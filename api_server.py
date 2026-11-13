import os
from v1 import create_app

if __name__ == "__main__":
    from waitress import serve
    serve(create_app(), host=os.environ.get("MONCACAO_HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
