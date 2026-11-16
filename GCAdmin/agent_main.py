import sys

if __name__ == '__main__':
    if '--console-stop' in sys.argv:
        from gcadmin.console_stop import send
        try:
            send(int(sys.argv[sys.argv.index('--console-stop') + 1]))
        except Exception:
            sys.exit(1)
    else:
        from gcadmin.agent import main
        main()
