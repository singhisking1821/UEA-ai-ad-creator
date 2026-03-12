from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_SECRET: str
    TELEGRAM_ALLOWED_CHAT_ID: int

    ANTHROPIC_API_KEY: str

    HEYGEN_API_KEY: str

    PEXELS_API_KEY: str

    SHOTSTACK_API_KEY: str
    SHOTSTACK_ENV: str = 'v1'

    GOOGLE_SERVICE_ACCOUNT_JSON: str
    GOOGLE_SHEET_ID: str
    GOOGLE_DRIVE_FOLDER_ID: str

    BASE_URL: str
    MAX_ADS_PER_BATCH: int = 10
    MAX_VIDEO_SECONDS: int = 22


settings = Settings()
