---
description: how to commit and push code to GitHub
---

# Push FaceFlow AI to GitHub

// turbo-all

1. Stage all changes

```
git add .
```

2. Commit with a message (replace "your message" with what changed)

```
git commit -m "your message"
```

3. Push to GitHub

```
git push
```

## Quick one-liner (PowerShell)

Run each command separately — PowerShell does not support `&&`:

```
git add .
git commit -m "update"
git push
```

## Notes

- `.env` is gitignored — your API keys are NEVER pushed
- Remote: https://github.com/sushantmaharaj/faceflow-ai
- Branch: `main`
