from dulwich.repo import Repo
from dulwich.porcelain import status, add, commit

repo = Repo('.')
# Stage all files
add(repo)

# Check status
st = status(repo)
added_count = len(st.staged.get('add', []))
print(f"Staged files count: {added_count}")

# Make initial commit
commit_id = commit(
    repo,
    message=b"feat: Runbhoomi Box Cricket Enterprise Dual Portal with Supabase Sync",
    committer=b"Prakhar <runbhoomiboxcricketup@gmail.com>",
    author=b"Prakhar <runbhoomiboxcricketup@gmail.com>"
)
print(f"Committed successfully! Commit Hash: {commit_id.decode('ascii')}")
