import sys

from gui.setup_window import run_setup_if_needed
from gui.app import App


def main():
    if not run_setup_if_needed():
        sys.exit(1)
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
