import subprocess
import os
import sys
import argparse
import glob
from datetime import datetime
from datetime import timedelta

from util import *

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("ingress", help="the path to ingress from")
    parser.add_argument("egress", help="the path to egress to")
    parser.add_argument("stmap", help="the path to the stmap file")
    parser.add_argument("-o", "--organize", help="create a folder structure of year-mm-dd/ at the egress", action="store_true", default=True)
    parser.add_argument("--cuda", help="use CUDA accelerated operations", action="store_true", default=True)
    parser.add_argument('--no-cuda', dest='cuda', action='store_false')

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    ingress = args.ingress
    egress = args.egress
    organize = args.organize
    cuda = args.cuda

    # check if the ingress directory exists
    if not os.path.exists(ingress):
        print(f"The ingress directory {ingress} does not exist.")
        sys.exit(1)
    
    # check if the egress directory exists, or create it
    if not os.path.exists(egress):
        os.makedirs(egress)
        print(f"The egress directory {egress} does not exist. Created it.")

    # Get all video files in the ingress directory
    videos = glob.glob(os.path.join(ingress, "*/*.mp4"))



if __name__ == "__main__":
    main()
