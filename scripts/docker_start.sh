#!/usr/bin/env sh
set -eu
python -m hospital.pipeline --generate --backend mysql
exec python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
