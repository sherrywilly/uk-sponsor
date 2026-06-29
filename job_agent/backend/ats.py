from __future__ import annotations

from urllib.parse import urlparse


def domain_from_url(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


def detect_ats_type(url: str) -> str:
    domain = domain_from_url(url)
    if "greenhouse.io" in domain or "boards.greenhouse.io" in domain:
        return "greenhouse"
    if "jobs.lever.co" in domain:
        return "lever"
    if "myworkdayjobs.com" in domain:
        return "workday"
    if "jobs.ashbyhq.com" in domain:
        return "ashby"
    if "careers.smartrecruiters.com" in domain:
        return "smartrecruiters"
    if "bamboohr.com" in domain:
        return "bamboohr"
    return "custom"
