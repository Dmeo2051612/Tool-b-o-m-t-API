# Finora pre-commit audit — fixed PowerShell script

This version fixes a PowerShell parsing issue in the review-message output by using the `-f` format operator instead of interpolating `$_` property expressions inside the string. It is saved as UTF-8 with BOM for Windows PowerShell 5.1 compatibility.

## Replace the script

Copy `audit_finora_before_commit.ps1` over the existing file in the root of your `Expense_management_app` repository.

## Run

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\audit_finora_before_commit.ps1
```

The execution-policy override only applies to the current PowerShell process. This script does not stage, edit, delete, upload, or commit any project files. It prints warnings for review; manually inspect them and the staged diff before committing. Pattern scanning is heuristic and cannot guarantee that all secrets are absent.
