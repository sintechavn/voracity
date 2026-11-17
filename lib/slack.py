import socket
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from voracity2 import settings
from voracity2.lib.utils import dicts_to_mrkdwn_table


class Slack:
    def __init__(self, token=None) -> None:
        self.host_name = "Host Name: " + socket.gethostname()
        self.client = WebClient(token=token or settings.SLACK_BEARER_TOKEN, timeout=300)

    def send_message(self, message: str, channel, mrkdown: bool = True):
        try:
            self.client.chat_postMessage(
                channel=channel,
                text=message,
                mrkdwn=mrkdown,
            )
        except SlackApiError as e:
            print(f"DEBUG: Got an error: {e.response['error']}")

    def send_file(self, file_path: str, message: str, channel: str):
        fpath = Path(file_path)
        client = WebClient(token="xoxb-10026777183396-10044576862017-SCxfOHIU0wx0MbQy2jFezLbl", timeout=300)
        response = client.files_upload_v2(
            channel=channel,
            filename=fpath.name,
            file=file_path,
            initial_comment=message,
        )
        if response is None:
            return
        return response
 
    def send_file_real(self, file_path: str, message: str):
        fpath = Path(file_path)
        response = self.client.files_upload_v2(
            channel="C0A3LEF26Q7",
            filename=fpath.name,
            file=file_path,
            initial_comment=message,
        )
        if response is None:
            return
        return response  

    def send_text_table(self, data: list[dict], channel: str):
        """
        Send job progress to Slack.
        """
        # Slackに進捗状況を送信する
        # ここでは、SlackのAPIを使用して進捗状況を送信する処理を実装します。
        if len(data) == 0:
            return

        Slack().send_message(
            channel=channel,
            message=dicts_to_mrkdwn_table(data),
            mrkdown=True,
        )

    def send_message_test(self, message: str, channel: str, mrkdown: bool = True):
        token = "xoxb-9981229251267-9991254848148-yMjZRAJY8yIx01qvllgQEtmH"
        client = WebClient(token=token, timeout=300)
        try:
            client.chat_postMessage(
                channel=channel,
                text=message,
                mrkdown=mrkdown,
            )
        except SlackApiError as e:
            print(f"Got an error: {e.response['error']}")

if __name__ == "__main__":
    Slack().send_message("テストメッセージ")
