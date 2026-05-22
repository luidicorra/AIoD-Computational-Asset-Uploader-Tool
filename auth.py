"""Command-line helper for creating and validating an AIoD SDK token."""

import aiod

if __name__ == "__main__":
    aiod.create_token(write_to_file=True)
    print("Authenticated as:")
    print(aiod.get_current_user())
