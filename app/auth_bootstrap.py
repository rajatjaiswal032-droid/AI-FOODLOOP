import argparse
import getpass

from app.core.auth import bootstrap_admin


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first AI FOODLOOP administrator.")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Administrator password: ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        parser.error("passwords do not match")
    try:
        bootstrap_admin(args.username, password)
    except ValueError as error:
        parser.error(str(error))
    print("Administrator account created.")


if __name__ == "__main__":
    main()
