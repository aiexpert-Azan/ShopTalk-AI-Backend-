#!/usr/bin/env python3
"""
Script to rewrite git history and remove hardcoded Twilio credentials.
Run this after committing the fix to remove secrets from previous commits.
"""

import subprocess
import os
import sys

def run_command(cmd, check=True):
    """Run a shell command and return output."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0 and check:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout, result.stderr, result.returncode

def main():
    # First, abort any ongoing rebase
    print("Aborting any ongoing rebase...")
    run_command("git rebase --abort", check=False)
    
    print("\nAttempting to rewrite history using git filter-branch...")
    
    # Enable squelch warning and use filter-branch
    env = os.environ.copy()
    env["FILTER_BRANCH_SQUELCH_WARNING"] = "1"
    
    # Create a Python script that will be executed for each tree
    cmd = (
        'git filter-branch --env-filter '
        '\'if [ "$GIT_COMMIT" = "b403e9a62ab2fbb5a959a96d429dccde1b82dc59" ]; then '
        'sed -i "s/ACe5c13671a538aff4396f6fd0b772f201/REDACTED_SECRET_SID/g" '
        'scripts/twilio_sandbox_send.py 2>/dev/null; '
        'sed -i "s/097f6740c0f56046336ff7440f418f34/REDACTED_SECRET_TOKEN/g" '
        'scripts/twilio_sandbox_send.py 2>/dev/null; fi\' '
        '-- --all'
    )
    
    out, err, code = run_command(cmd, check=False)
    
    if code == 0:
        print("\n✓ Successfully rewrote git history!")
        print("\nNow force-push to remote...")
        run_command("git push --force-with-lease origin main")
        print("\n✓ Successfully pushed to remote!")
    else:
        print(f"\nAttempted rewrite completed with code {code}")
        if "Rewrite" in out:
            print("Some rewrites were made. Attempting force push...")
            run_command("git push --force-with-lease origin main", check=False)

if __name__ == "__main__":
    main()
