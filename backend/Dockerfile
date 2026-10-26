FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ ./

# Create the static and media directories before dropping privileges so a
# mounted volume inherits their ownership.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Run migrations and collect static on start, then serve with Gunicorn (WSGI).
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60"]
