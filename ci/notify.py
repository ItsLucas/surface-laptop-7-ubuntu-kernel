#!/usr/bin/env python3
"""Open/update one GitHub issue and mention the owner when automated builds fail."""
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

TITLE = 'Ubuntu 26.10 自动内核构建失败 / Automated kernel build failure'


def api(path, method='GET', payload=None):
    request = urllib.request.Request('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + path,
        method=method, data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
                 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    run_url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    issues = api('/issues?state=open&per_page=100')
    existing = next((i for i in issues if i['title'] == TITLE and 'pull_request' not in i), None)
    if os.environ.get('BUILD_RESULT') == 'success':
        if existing:
            api(f"/issues/{existing['number']}/comments", 'POST', {'body': f'当前构建和签名已成功：[运行记录]({run_url})。产物仍需本地initrd和实机验收。'})
            api(f"/issues/{existing['number']}", 'PATCH', {'state': 'closed'})
        return
    body = (f"@{os.environ['GITHUB_REPOSITORY_OWNER']} 自动构建失败，需要检查。\n\n"
            f"运行记录：{run_url}\n\n提交：`{os.environ['GITHUB_SHA']}`\n\n"
            f"阶段结果：`{os.environ.get('JOB_RESULTS', 'unknown')}`\n\n"
            '请查看失败步骤及诊断附件中的 patches.log / build.log。补丁冲突不会被跳过，也不会自动安装或更改本机内核。'
            '\n\n修复并完成一次成功构建后，此 Issue 自动关闭。')
    if existing:
        api(f"/issues/{existing['number']}/comments", 'POST', {'body': body})
    else:
        api('/issues', 'POST', {'title': TITLE, 'body': body})


if __name__ == '__main__':
    main()
