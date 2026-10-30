import type { BrowserContext, Page } from '@playwright/test'

// 仅在验收上下文观察原生连接；不改变 ICE 配置，不注入产品页面产物。
export async function observeTransfers(context: BrowserContext) {
  await context.addInitScript(() => {
    const Native = window.RTCPeerConnection
    type Entry = { pc: RTCPeerConnection; started: number; connectedMs: number | null }
    const entries: Entry[] = []
    ;(window as unknown as { __transferTestPeers: Entry[] }).__transferTestPeers = entries
    window.RTCPeerConnection = class extends Native {
      constructor(configuration?: RTCConfiguration) {
        super(configuration)
        const entry: Entry = { pc: this, started: performance.now(), connectedMs: null }
        entries.push(entry)
        this.addEventListener('connectionstatechange', () => {
          if (this.connectionState === 'connected' && entry.connectedMs === null) entry.connectedMs = Math.round(performance.now() - entry.started)
        })
      }
    }
  })
}

export async function transferDiagnostics(page: Page) {
  return page.evaluate(async () => {
    const entries = (window as unknown as { __transferTestPeers?: { pc: RTCPeerConnection; started: number; connectedMs: number | null }[] }).__transferTestPeers || []
    return Promise.all(entries.map(async ({ pc, started, connectedMs }) => {
      // 只统计候选数量，不保存 SDP 或候选地址。
      const described = (description: RTCSessionDescription | null) => {
        const candidates = (description?.sdp || "").split(/\r?\n/).filter(line => line.startsWith("a=candidate:"))
        return { present: description !== null, candidates: candidates.length, mdns: candidates.filter(line => /\.local(?:\s|$)/.test(line)).length }
      }
      const result = {
        statsScope: 'final-snapshot',
        descriptions: { local: described(pc.localDescription), remote: described(pc.remoteDescription) },
        connection: pc.connectionState, iceConnection: pc.iceConnectionState,
        iceGathering: pc.iceGatheringState, signaling: pc.signalingState,
        elapsedMs: Math.round(performance.now() - started), connectedMs,
        candidates: { local: { host: 0, srflx: 0, prflx: 0, relay: 0, other: 0 }, remote: { host: 0, srflx: 0, prflx: 0, relay: 0, other: 0 } },
        pairs: { waiting: 0, 'in-progress': 0, failed: 0, succeeded: 0, frozen: 0, other: 0 },
        nominatedPairs: 0, channels: 0, bytesSent: 0, bytesReceived: 0, statsAvailable: true,
      }
      try {
        const stats = await pc.getStats()
        stats.forEach(stat => {
          if (stat.type === 'local-candidate' || stat.type === 'remote-candidate') {
            const side = stat.type === 'local-candidate' ? result.candidates.local : result.candidates.remote
            const kind = ['host', 'srflx', 'prflx', 'relay'].includes(stat.candidateType) ? stat.candidateType as 'host' | 'srflx' | 'prflx' | 'relay' : 'other'
            side[kind]++
          } else if (stat.type === 'candidate-pair') {
            const state = ['waiting', 'in-progress', 'failed', 'succeeded', 'frozen'].includes(stat.state) ? stat.state as 'waiting' | 'in-progress' | 'failed' | 'succeeded' | 'frozen' : 'other'
            result.pairs[state]++
            if (stat.nominated === true) result.nominatedPairs++
          } else if (stat.type === 'data-channel') {
            result.channels++
            result.bytesSent += Number.isFinite(stat.bytesSent) ? stat.bytesSent : 0
            result.bytesReceived += Number.isFinite(stat.bytesReceived) ? stat.bytesReceived : 0
          }
        })
      } catch { result.statsAvailable = false }
      return result
    }))
  }).catch(() => ({ unavailable: true }))
}
