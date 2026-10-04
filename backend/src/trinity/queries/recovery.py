"""Recover expired SQL reservations without serving HTTP or running refreshes."""
import time
from trinity.adapters.postgres import Database
from trinity.config import load_api_settings
from trinity.queries.config import execution_factory


def main():
    """Reconcile at startup and periodically; never release unknown execution."""
    database=Database(load_api_settings());database.open()
    try:
        while True:
            execution=None
            try:
                execution=execution_factory(database,recovery=True)
                for _ in range(4):
                    if not execution.recover_one():break
            except Exception:
                pass
            finally:
                if execution is not None:execution.close()
            time.sleep(2)
    finally:database.close()


if __name__=='__main__':main()
