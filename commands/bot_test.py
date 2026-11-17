import click
from seleniumbase import SB

@click.command()
def bot_test():
    """
    Command to test the bot functionality.
    """

    with SB(uc=True, headless=False) as sb:
        sb.open("https://deviceandbrowserinfo.com/are_you_a_bot")
        input("Press Enter to continue...")
        # sb.assert_text("You are a bot", "body")

    click.echo("Bot test command executed successfully.")