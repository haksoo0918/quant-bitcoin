# -*- coding: utf-8 -*-
import requests
import logging
from config import DISCORD_WEBHOOK_URL, DRY_RUN

# 기본 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def send_discord_message(content: str):
    """
    디스코드 채널로 텍스트 메시지를 전송합니다.
    """
    if not DISCORD_WEBHOOK_URL:
        logging.warning("디스코드 웹훅 URL이 설정되지 않았습니다. 메시지 전송을 건너뜁니다.")
        print(f"[Discord Bypass]\n{content}")
        return False

    payload = {"content": content}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 204):
            logging.info("디스코드 메시지가 성공적으로 전송되었습니다.")
            return True
        else:
            logging.error(f"디스코드 메시지 전송 실패 (상태 코드: {response.status_code}): {response.text}")
            return False
    except Exception as e:
        logging.error(f"디스코드 웹훅 연동 예외 발생: {e}")
        return False

def make_bold(text: str) -> str:
    return f"**{text}**"

def make_code(text: str) -> str:
    return f"`{text}`"
