import os
import sys
from dulwich.repo import Repo
from dulwich.porcelain import status, add, commit, push

token = os.environ.get("GH_PAT")
if not token:
    print("Error: No GH_PAT environment variable provided.")
    sys.exit(1)

repo = Repo('.')
add(repo)
st = status(repo)
print("Staged files:", st.staged)

commit_id = commit(
    repo,
    message=b"feat: Add Admin customer lookup & directory, dynamic payment QR, and Google Maps Locate Us",
    committer=b"Prakhar <runbhoomiboxcricketup@gmail.com>",
    author=b"Prakhar <runbhoomiboxcricketup@gmail.com>"
)
print(f"Committed: {commit_id.decode('ascii')}")

auth_url = f"https://Prakhar2404:{token}@github.com/Prakhar2404/runbhoomi_box_cricket.git"
print("Pushing to GitHub...")
try:
    push(repo, auth_url, refspecs=b"refs/heads/master:refs/heads/main", force=True)
    print("SUCCESS: Pushed cleanly to GitHub main branch!")
except Exception as e:
    print(f"Push failed: {e}")
    sys.exit(1)
