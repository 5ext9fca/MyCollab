#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    time::{Duration, Instant},
};
use tauri::{Manager, State};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_updater::UpdaterExt;

#[derive(Default)]
struct Runner {
    child: Option<Child>,
    exit_code: Option<i32>,
}
#[derive(Default)]
struct Runtime {
    runner: Mutex<Runner>,
    updating: AtomicBool,
}
struct UpdateGuard<'a>(&'a AtomicBool);
impl Drop for UpdateGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}
#[derive(Serialize, Deserialize, Clone, Default)]
struct Config {
    server: String,
    device_token: String,
    model: String,
    #[serde(default)]
    opencode: String,
    #[serde(default)]
    ca_file: String,
}

fn config_path() -> Result<PathBuf, String> {
    #[cfg(debug_assertions)]
    if let Some(path) = std::env::var_os("MYCOLLAB_COMPANION_TEST_CONFIG") {
        return Ok(PathBuf::from(path));
    }
    let home = std::env::var_os("HOME").ok_or("无法定位用户目录")?;
    Ok(PathBuf::from(home).join(".config/MyCollab/mycollab-runner.json"))
}
fn read_private() -> Result<Config, String> {
    let path = config_path()?;
    if !path.exists() {
        return Ok(Config::default());
    }
    let meta = fs::metadata(&path).map_err(|_| "无法读取配置")?;
    use std::os::unix::fs::PermissionsExt;
    if meta.permissions().mode() & 0o077 != 0 {
        return Err("配置权限过宽，请设置为 0600".into());
    }
    if meta.len() > 16384 {
        return Err("配置文件过大".into());
    }
    serde_json::from_slice(&fs::read(path).map_err(|_| "无法读取配置")?)
        .map_err(|_| "配置格式无效".into())
}
fn validate(config: &Config) -> Result<(), String> {
    let url = url::Url::parse(&config.server).map_err(|_| "网站地址无效")?;
    let local = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"));
    if !(url.scheme() == "https" || (url.scheme() == "http" && local))
        || url.host_str().is_none()
        || url.username() != ""
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != "/"
    {
        return Err("仅允许 HTTPS 站点根地址；本机 localhost 可用 HTTP".into());
    }
    if config.device_token.is_empty()
        || config.device_token.len() > 128
        || !config.device_token.is_ascii()
        || config.device_token.chars().any(char::is_whitespace)
    {
        return Err("请填写有效的设备凭据".into());
    }
    if config.model.trim().is_empty() || config.model.len() > 200 {
        return Err("请填写模型名称".into());
    }
    if !PathBuf::from(&config.opencode).is_absolute() || !PathBuf::from(&config.opencode).is_file()
    {
        return Err("请选择已安装 OpenCode 的完整可执行文件路径".into());
    }
    if !config.ca_file.is_empty() && !PathBuf::from(&config.ca_file).is_file() {
        return Err("CA 证书文件不存在".into());
    }
    Ok(())
}
fn poll(runner: &mut Runner) -> Result<bool, String> {
    if let Some(child) = runner.child.as_mut() {
        match child.try_wait().map_err(|_| "无法读取 Runner 状态")? {
            Some(status) => {
                runner.exit_code = status.code();
                runner.child = None;
            }
            None => return Ok(true),
        }
    }
    Ok(false)
}
fn sidecar_path() -> Result<PathBuf, String> {
    let executable = std::env::current_exe().map_err(|_| "无法定位应用")?;
    let bundled = executable
        .parent()
        .ok_or("无法定位应用目录")?
        .join("mycollab-runner");
    if bundled.is_file() {
        return Ok(bundled);
    }
    #[cfg(debug_assertions)]
    {
        let target = if cfg!(target_arch = "aarch64") {
            "aarch64-apple-darwin"
        } else {
            "x86_64-apple-darwin"
        };
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join(format!("binaries/mycollab-runner-{target}"));
        if dev.is_file() {
            return Ok(dev);
        }
    }
    Err("缺少随应用打包的 Runner，请重新安装完整应用".into())
}
fn sidecar_command() -> Result<Command, String> {
    let mut command = Command::new(sidecar_path()?);
    command
        .arg("--config")
        .arg(config_path()?)
        .stdin(Stdio::null());
    // Finder 启动不继承交互 shell 的 PATH；保留用户路径并补充常见 CLI 安装位置。
    let path = std::env::var("PATH").unwrap_or_default();
    command.env(
        "PATH",
        format!("{path}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"),
    );
    Ok(command)
}
fn query(mode: &str) -> Result<Value, String> {
    // 参数只能由内部固定调用点选择，不向 WebView 暴露任意命令执行。
    let mut child = sidecar_command()?
        .arg(mode)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "无法启动诊断进程")?;
    let deadline = Instant::now() + Duration::from_secs(40);
    loop {
        if let Some(status) = child.try_wait().map_err(|_| "诊断进程异常")? {
            if !status.success() {
                return Err("诊断失败，请检查配置权限和 OpenCode 安装路径".into());
            }
            let output = child.wait_with_output().map_err(|_| "无法读取诊断结果")?;
            if output.stdout.len() > 65536 {
                return Err("诊断结果过大".into());
            }
            return serde_json::from_slice(&output.stdout).map_err(|_| "诊断结果格式无效".into());
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("诊断超时，请检查网络".into());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

#[tauri::command]
fn read_config(app: tauri::AppHandle) -> Result<Value, String> {
    let config = read_private()?;
    let opencode = if config.opencode.is_empty() || config.opencode == "opencode" {
        ["/opt/homebrew/bin/opencode", "/usr/local/bin/opencode"]
            .iter()
            .find(|p| PathBuf::from(p).is_file())
            .unwrap_or(&"")
            .to_string()
    } else {
        config.opencode
    };
    Ok(
        json!({"server":config.server,"model":config.model,"opencode":opencode,"ca_file":config.ca_file,"token_present":!config.device_token.is_empty(),
        "autostart":app.autolaunch().is_enabled().map_err(|_| "无法读取登录启动设置")?}),
    )
}
#[tauri::command]
fn save_config(mut config: Config, state: State<Runtime>) -> Result<(), String> {
    let mut runner = state.runner.lock().map_err(|_| "进程状态不可用")?;
    if poll(&mut runner)? {
        return Err("请先停止 Runner 再修改配置".into());
    }
    let previous = match read_private() {
        Ok(value) => value,
        Err(_) if !config.device_token.is_empty() => Config::default(),
        Err(error) => return Err(error),
    };
    config.server = config.server.trim().trim_end_matches('/').to_string();
    config.model = config.model.trim().to_string();
    config.opencode = config.opencode.trim().to_string();
    if config.device_token.is_empty() && config.server == previous.server.trim_end_matches('/') {
        config.device_token = previous.device_token;
    }
    validate(&config)?;
    let path = config_path()?;
    let parent = path.parent().ok_or("配置目录无效")?;
    fs::create_dir_all(parent).map_err(|_| "无法创建配置目录")?;
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
    fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
        .map_err(|_| "无法保护配置目录")?;
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| "系统时钟无效")?
        .as_nanos();
    let pending = parent.join(format!(
        ".companion-config-{}-{nonce}.pending",
        std::process::id()
    ));
    let mut stream = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&pending)
        .map_err(|_| "无法创建配置临时文件，请检查是否有未完成保存")?;
    let outcome = (|| {
        stream
            .write_all(&serde_json::to_vec(&config).map_err(|_| "配置编码失败")?)
            .map_err(|_| "配置写入失败")?;
        stream.sync_all().map_err(|_| "配置同步失败")?;
        fs::rename(&pending, path).map_err(|_| "配置替换失败")
    })();
    if outcome.is_err() {
        let _ = fs::remove_file(pending);
    }
    Ok(outcome?)
}
#[tauri::command]
fn start_runner(state: State<Runtime>) -> Result<(), String> {
    validate(&read_private()?)?;
    let mut runner = state.runner.lock().map_err(|_| "进程状态不可用")?;
    if state.updating.load(Ordering::SeqCst) {
        return Err("正在更新，请稍后启动 Runner".into());
    }
    if poll(&mut runner)? {
        return Ok(());
    }
    let child = sidecar_command()?
        .arg("--parent-pid")
        .arg(std::process::id().to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "无法启动 Runner")?;
    runner.child = Some(child);
    runner.exit_code = None;
    Ok(())
}
fn stop(state: &Runtime) -> Result<(), String> {
    let mut runner = state.runner.lock().map_err(|_| "进程状态不可用")?;
    if let Some(child) = runner.child.as_mut() {
        unsafe {
            libc::kill(child.id() as i32, libc::SIGTERM);
        }
        let deadline = Instant::now() + Duration::from_secs(12);
        while child.try_wait().map_err(|_| "无法停止 Runner")?.is_none() {
            if Instant::now() >= deadline {
                return Err("Runner 正在清理，请稍后再次停止".into());
            }
            std::thread::sleep(Duration::from_millis(100));
        }
    }
    poll(&mut runner)?;
    runner.exit_code = Some(0);
    Ok(())
}
#[tauri::command]
async fn stop_runner(app: tauri::AppHandle) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || stop(&app.state::<Runtime>()))
        .await
        .map_err(|_| "停止任务异常")?
}
fn status_file_path(config: &Config, path: &std::path::Path) -> Result<PathBuf, String> {
    let identity = format!(
        "{:x}",
        Sha256::digest(
            format!(
                "{}\0{}",
                config.server.trim_end_matches('/'),
                config.device_token
            )
            .as_bytes()
        )
    );
    Ok(path
        .parent()
        .ok_or("配置目录无效")?
        .join("runner-state")
        .join(identity)
        .join("status.json"))
}
fn read_status_file(config: &Config) -> Result<Value, String> {
    let path = status_file_path(config, &config_path()?)?;
    match fs::File::open(path) {
        Ok(file) => {
            let mut bytes = Vec::new();
            file.take(65537)
                .read_to_end(&mut bytes)
                .map_err(|_| "无法读取运行状态")?;
            if bytes.len() > 65536 {
                return Err("运行状态文件过大".into());
            }
            let value: Value =
                serde_json::from_slice(&bytes).map_err(|_| "运行状态文件格式无效")?;
            Ok(
                json!({"state":value.get("state"), "updated_at":value.get("updated_at"),
                "pending_results":value.get("pending_results"), "rejected_results":value.get("rejected_results")}),
            )
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(json!({})),
        Err(_) => Err("无法读取运行状态".into()),
    }
}

#[tauri::command]
async fn runner_status(app: tauri::AppHandle) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let config = read_private()?;
        let state = app.state::<Runtime>();
        let mut runner = state.runner.lock().map_err(|_| "进程状态不可用")?;
        let running = poll(&mut runner)?;
        let exit = runner.exit_code;
        drop(runner);
        let configured = !config.device_token.is_empty();
        let detail = if configured {
            read_status_file(&config)?
        } else {
            json!({})
        };
        Ok(json!({"running":running,"exit_code":exit,"configured":configured,"detail":detail}))
    })
    .await
    .map_err(|_| "状态读取任务异常")?
}
#[tauri::command]
async fn diagnose() -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(|| query("--diagnose"))
        .await
        .map_err(|_| "诊断任务异常")?
}
#[tauri::command]
fn set_autostart(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    if enabled {
        app.autolaunch().enable()
    } else {
        app.autolaunch().disable()
    }
    .map_err(|_| "无法更新登录启动设置".into())
}
#[tauri::command]
fn open_website() -> Result<(), String> {
    let config = read_private()?;
    validate(&config)?;
    Command::new("/usr/bin/open")
        .arg(config.server)
        .spawn()
        .map_err(|_| "无法打开浏览器")?;
    Ok(())
}
#[tauri::command]
async fn check_update(app: tauri::AppHandle) -> Result<String, String> {
    let state = app.state::<Runtime>();
    if state.updating.swap(true, Ordering::SeqCst) {
        return Err("已在检查更新".into());
    }
    let _guard = UpdateGuard(&state.updating);
    {
        let mut runner = state.runner.lock().map_err(|_| "进程状态不可用")?;
        if poll(&mut runner)? {
            return Err("请先停止 Runner 再安装更新".into());
        }
    }
    // 发布端点和公钥在签名发布构建时注入，禁止用户内容修改更新来源。
    let (endpoint, pubkey) = match (
        option_env!("MYCOLLAB_UPDATE_URL"),
        option_env!("MYCOLLAB_UPDATE_PUBLIC_KEY"),
    ) {
        (Some(url), Some(key)) => (url, key),
        _ => return Ok("此本地构建未配置签名更新源，请安装维护者提供的新版本。".into()),
    };
    let url = url::Url::parse(endpoint).map_err(|_| "更新地址无效")?;
    if url.scheme() != "https" {
        return Err("更新源必须使用 HTTPS".into());
    }
    let updater = app
        .updater_builder()
        .pubkey(pubkey)
        .endpoints(vec![url])
        .map_err(|_| "更新配置无效")?
        .build()
        .map_err(|_| "无法创建更新器")?;
    if let Some(update) = updater.check().await.map_err(|_| "无法检查签名更新")? {
        update
            .download_and_install(|_, _| {}, || {})
            .await
            .map_err(|_| "签名校验或更新安装失败，未完成更新")?;
        Ok("更新已安装，请从菜单栏退出并重新打开应用。".into())
    } else {
        Ok("当前已是最新版本。".into())
    }
}
fn show(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show(app)))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--autostart"]),
        ))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(Runtime::default())
        .invoke_handler(tauri::generate_handler![
            read_config,
            save_config,
            start_runner,
            stop_runner,
            runner_status,
            diagnose,
            set_autostart,
            open_website,
            check_update
        ])
        .setup(|app| {
            use tauri::menu::{Menu, MenuItem};
            let open = MenuItem::with_id(app, "show", "打开本地伴侣", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "停止并退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            let icon = app.default_window_icon().ok_or("缺少应用图标")?.clone();
            tauri::tray::TrayIconBuilder::new()
                .icon(icon)
                .tooltip("MyCollab 本地伴侣")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show(app),
                    "quit" => {
                        let app = app.clone();
                        tauri::async_runtime::spawn_blocking(move || {
                            if stop(&app.state::<Runtime>()).is_ok() {
                                app.exit(0);
                            } else {
                                show(&app);
                            }
                        });
                    }
                    _ => (),
                })
                .build(app)?;
            if std::env::args().any(|arg| arg == "--autostart") {
                let _ = start_runner(app.state::<Runtime>());
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("无法启动 MyCollab 本地伴侣")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let _ = stop(&app.state::<Runtime>());
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> Config {
        Config {
            server: "https://example.com".into(),
            device_token: "mc_agent_test".into(),
            model: "provider/model".into(),
            opencode: "/usr/bin/true".into(),
            ca_file: String::new(),
        }
    }
    #[test]
    fn restrict_server_and_executable() {
        assert!(validate(&config()).is_ok());
        for url in [
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com/path",
            "https://example.com?token=secret",
            "file:///tmp/a",
        ] {
            let mut value = config();
            value.server = url.into();
            assert!(validate(&value).is_err());
        }
        let mut value = config();
        value.opencode = "echo injected".into();
        assert!(validate(&value).is_err());
    }
    #[test]
    fn state_identity_matches_python_runner() {
        let value = config();
        let path = status_file_path(&value, std::path::Path::new("/tmp/runner.json")).unwrap();
        assert!(path.ends_with("runner-state/7b03ce63a65db357baf136a4015170b04b7882e14a0b0c35212b6b6e7017a9f7/status.json"));
        let mut trailing = value.clone();
        trailing.server.push('/');
        assert_eq!(
            path,
            status_file_path(&trailing, std::path::Path::new("/tmp/runner.json")).unwrap()
        );
    }
    #[test]
    fn explicit_stop_is_not_reported_as_crash() {
        let runtime = Runtime::default();
        runtime.runner.lock().unwrap().child =
            Some(Command::new("/bin/sleep").arg("30").spawn().unwrap());
        stop(&runtime).unwrap();
        let mut runner = runtime.runner.lock().unwrap();
        assert!(!poll(&mut runner).unwrap());
        assert_eq!(runner.exit_code, Some(0));
    }
    #[test]
    fn update_guard_restores_start_permission_on_error() {
        let flag = AtomicBool::new(true);
        {
            let _guard = UpdateGuard(&flag);
        }
        assert!(!flag.load(Ordering::SeqCst));
    }
    #[test]
    fn process_poll_records_exit() {
        let child = Command::new("/usr/bin/true").spawn().unwrap();
        let mut runner = Runner {
            child: Some(child),
            exit_code: None,
        };
        while poll(&mut runner).unwrap() {
            std::thread::sleep(Duration::from_millis(10));
        }
        assert_eq!(runner.exit_code, Some(0));
    }
}
