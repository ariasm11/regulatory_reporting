"""Reproducible measured local benchmark; does not claim BigQuery performance."""
import argparse
import resource
import time
import platform
from siter.common import ROOT, dump, load
from siter.generate import generate
from siter.run import execute


def main():
    p=argparse.ArgumentParser();p.add_argument('--transactions',type=int,default=1_000_000)
    p.add_argument('--customers',type=int,default=20_000);a=p.parse_args()
    started=time.perf_counter()
    dataset=generate(ROOT/'data/portfolio',a.transactions,a.customers)
    generation_seconds=round(time.perf_counter()-started,3)
    results=[]
    for period in load(ROOT/'config/reporting.json')['valid_periods']:
        dest,summary=execute(ROOT/'data/portfolio',ROOT/'output/portfolio',period)
        results.append(dict(period=period,reported_accounts=summary['reported_accounts'],
                            period_transactions=summary['quality']['period_transactions'],
                            model_seconds=summary['model_seconds'],total_seconds=summary['total_seconds'],
                            txt_bytes=summary['bytes'],txt_sha256=summary['txt_sha256'],record_counts=summary['record_counts']))
        print(period,summary['reported_accounts'],summary['total_seconds'],flush=True)
    report=dict(engine='Python streaming reference, not BigQuery',dataset=dataset,generation_seconds=generation_seconds,
                wall_seconds=round(time.perf_counter()-started,3),
                peak_rss_kib_linux=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                platform=platform.platform(),python=platform.python_version(),periods=results,
                notes='Each period scans the full CSV for global duplicate detection. No BigQuery timings or costs measured.')
    dump(ROOT/'examples/benchmark.json',report)


if __name__=='__main__':main()
