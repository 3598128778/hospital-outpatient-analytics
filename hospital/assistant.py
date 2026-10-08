import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse
from .analytics import totals
from .config import ROOT


def build_payload(rows, alerts, scope):
    return {'data_source': 'synthetic', 'scope': scope, 'metrics': totals(rows),
        'anomaly_scope': '科室全天；只按日期和科室筛选',
        'anomaly_count': len(alerts), 'anomalies_sent': min(len(alerts), 20), 'anomalies': alerts[:20]}


def rule_summary(payload):
    m, s = payload['metrics'], payload['scope']
    average = '不可计算' if m['avg_spend'] is None else f"¥{m['avg_spend']:,.2f}"
    return (f"### 运营摘要\n规则摘要（未调用大模型）；数据为模拟数据。\n\n"
        f"期间：{s['start']} 至 {s['end']}；科室：{s['department']}；时段：{s['period']}。\n\n"
        f"有效挂号 {m['registrations']:,} 人次，完成就诊 {m['visits']:,} 人次，"
        f"净收费 ¥{m['net_cents']/100:,.2f}，每就诊人次净收费 {average}。\n\n"
        f"### 异常提示\n选中日期和科室的全天异常共 {payload['anomaly_count']} 条；"
        f"时段筛选不改变全天异常检测范围。\n\n"
        "### 待验证假设\n异常可能与排班、季节性需求、收费结构或数据质量有关；尚无因果证据。\n\n"
        "### 建议核查步骤\n先检查隔离记录，再按异常日期、科室、时段查看挂号与收费明细，核对排班记录。")


def llm_summary(payload):
    base = os.environ.get('LLM_BASE_URL', '').rstrip('/')
    key, model = os.environ.get('LLM_API_KEY'), os.environ.get('LLM_MODEL')
    if not (base and key and model):
        raise ValueError('请设置 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL；或使用规则摘要。')
    parsed = urlparse(base)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('远程 LLM 地址必须使用 HTTPS。')
    body = {'model': model, 'temperature': .2, 'max_tokens': 1200, 'messages': [
        {'role': 'system', 'content': (ROOT / 'prompts/operations_summary.txt').read_text(encoding='utf-8')},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]}
    request = urllib.request.Request(base + '/chat/completions',
        data=json.dumps(body).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    # Never include request headers / provider response bodies in logs or user errors.
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
        answer = result['choices'][0]['message']['content']
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError()
        return answer
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'LLM 请求失败，HTTP {exc.code}；请检查服务配置或稍后重试。') from None
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, IndexError):
        raise RuntimeError('LLM 网络超时或响应格式无效；可切换到规则摘要。') from None
