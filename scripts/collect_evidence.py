"""Copy compact, reviewable release evidence for selected periods."""
import argparse
import shutil
from siter.common import ROOT, dump
from siter.run import execute


def main():
    p=argparse.ArgumentParser();p.add_argument('periods',nargs='+');a=p.parse_args()
    for period in a.periods:
        dest,summary=execute(ROOT/'data/portfolio',ROOT/'output/portfolio',period)
        example=ROOT/'examples/monthly'/period;example.mkdir(parents=True,exist_ok=True)
        for name in (summary['file'],'audit.json'):
            shutil.copyfile(dest/name,example/name)
        print(period,summary['reported_accounts'],summary['total_seconds'],flush=True)


if __name__=='__main__':main()
