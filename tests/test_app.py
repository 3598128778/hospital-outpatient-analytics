from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_dashboard_filters_and_rule_summary():
    if not Path('artifacts/run_report.json').exists():
        from hospital.pipeline import run
        from hospital.generate import generate
        from hospital.config import ROOT
        generate(ROOT / 'data/raw')
        run()
    app = AppTest.from_file('app.py', default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 4
    app.sidebar.selectbox[0].set_value('内科').run()
    assert not app.exception
    app.sidebar.selectbox[1].set_value('上午').run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert any('规则摘要（未调用大模型）' in block.value for block in app.markdown)
