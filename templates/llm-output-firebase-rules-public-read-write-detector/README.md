# llm-output-firebase-rules-public-read-write-detector

Static lint that flags Firebase / Firestore / Cloud Storage / Realtime
Database security rules that grant unconditional public read or write
to any client on the public internet.

## Why LLMs emit this

When a developer says "my Firestore client gets `Missing or
insufficient permissions`", an LLM's fastest path to a working app is
to relax the rules to allow everything. The model has seen this exact
shape thousands of times in tutorials, "getting started" guides, and
half-finished sample apps:

```firestore
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if true;
    }
  }
}
```

It is also the *literal default* in the Firebase console's "test
mode" wizard, with a 30-day timer that nobody re-reads. The LLM
cannot see the timer; it just sees the shape and emits it.

## What it catches

Per file, line-level findings:

- `allow read, write: if true;` (and any verb combination ending in
  `: if true`)
- `allow read;` / `allow write;` shorthand with no `if` guard, when
  the file looks like a Firestore / Storage rules file
- RTDB JSON: `".read": true` or `".write": true` (or
  `".read": "true"` string form)

Per file, whole-file finding:

- A wildcard `match /{document=**}` or root `match /` block whose
  body has any of the above public allows AND the file contains no
  `request.auth != null` / `request.auth.uid` / `auth != null` /
  `auth.uid` guard anywhere

## What it does NOT flag

- `allow read, write: if request.auth != null;`
- `allow read: if request.auth.uid == resource.data.ownerId;`
- `".read": "auth != null"` (RTDB auth check)
- Lines with a trailing `// fb-rules-public-ok` /
  `# fb-rules-public-ok` comment
- Files containing `fb-rules-public-ok-file` anywhere

## How to detect

```sh
python3 detector.py path/to/rules-dir/
```

Exit code = number of files with a finding (capped 255). Stdout:
`<file>:<line>:<reason>`.

## Safe pattern

Firestore:

```firestore
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
```

Realtime Database:

```json
{
  "rules": {
    "users": {
      "$uid": {
        ".read":  "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid"
      }
    }
  }
}
```

## Refs

- CWE-284: Improper Access Control
- CWE-732: Incorrect Permission Assignment for Critical Resource
- OWASP Mobile Top 10 (2024) M8: Security Misconfiguration
- Firebase docs: "Get started with Cloud Firestore Security Rules"
- Firebase blog (2022): "Why your database is exposed to the
  internet" — covers the test-mode default-public failure mode

## Verify

```sh
bash verify.sh
```

Should print `bad=5/5 good=0/3 PASS`.
