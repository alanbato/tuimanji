import getpass


def current_player() -> str:
    return getpass.getuser()
