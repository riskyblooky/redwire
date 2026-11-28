**SECRET**

# Red Team Assessment Report: Op Nightfall

**Client:** ACME &lt;Corp>  
**Date:** November 28, 2026

---

## (S) Executive Summary

ACME engaged us for **two weeks**. alert(1) Key risks:

1. Injection
2. AD hygiene


## (U) Findings

### (U) Severity Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 1 |
| MEDIUM | 1 |
| LOW | 1 |
| INFO | 1 |

### F01: (S) SQL injection in search

- **Severity:** CRITICAL
- **Affected Asset(s):** portal.acme.test, dc01
- **CVSS 3.1:** 9.8  |  CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H

#### Description

The **q** parameter is concatenated into SQL.

- union-based
- time-based

#### Impact

Full read of the `users` table.

#### Steps to Reproduce

1. Send `q='`
2. Observe the error

#### Technical Details

```sql
SELECT * FROM items WHERE name LIKE '%{q}%'
```

#### Recommendations

Use parameterised queries.

#### References

https://owasp.org/www-community/attacks/SQL_Injection

---

### F02: (C) Kerberoastable service account &lt;svc_sql>

- **Severity:** HIGH
- **Affected Asset(s):** dc01

#### Description

SPN set on a user account with a weak password & no AES.

#### Recommendations

Rotate to a gMSA.

---

### F03: (C) SMB signing not required

- **Severity:** MEDIUM
- **Affected Asset(s):** dc01

#### Description

Relay is possible.

---

### F04: (C) Missing HSTS

- **Severity:** LOW
- **Affected Asset(s):** portal.acme.test

#### Description

No `Strict-Transport-Security` header.

---

### F05: (U) Verbose server banner

- **Severity:** INFO
- **Affected Asset(s):** portal.acme.test

#### Description

The `Server` header discloses *nginx 1.24.0*.

---


## (U) Test Cases

3 test cases · 2 executed · 1 passed · 1 failed

| Mark | # | Title | Category | Status |
|------|---|-------|----------|--------|
| (C) | 1 | Kerberoasting | AD | Not Executed |
| (C) | 2 | Input validation | Web | Fail |
| (U) | 2.1 | SQLi in search | Web | Pass |

### 1 (C) Kerberoasting

- **Status:** Not Executed
- **Category:** AD

#### Description

Request TGS for SPN accounts.

### 2 (C) Input validation

- **Status:** Fail
- **Category:** Web

### 2.1 (U) SQLi in search

- **Status:** Pass
- **Category:** Web
- **Discovered Findings:** F01 SQL injection in search (Critical)

#### Steps

Fuzz `q`


## (U) Cleanup

| Mark | Title | Type | Status | Location |
|------|-------|------|--------|----------|
| (C) | Implant on dc01 | File | Pending | C:\Windows\Temp\a.exe |
| (C) | Test account | Account | Cleaned | CORP\rw_test |

### 1. (C) Implant on dc01

- **Type:** File
- **Status:** Pending
- **Location:** C:\Windows\Temp\a.exe
- **Affected Asset(s):** dc01

#### Description

Beacon dropped during lateral movement.

---

### 2. (C) Test account

- **Type:** Account
- **Status:** Cleaned
- **Location:** CORP\rw_test

#### Description

Created for the spray.

---


## (U) Appendix

| Tool | Version |
|---|---|
| nmap | 7.94 |


_Distribution limited to the client._

**SECRET**
