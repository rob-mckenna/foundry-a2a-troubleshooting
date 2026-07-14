# Customer Troubleshooting Package

This folder contains only the files customers need to troubleshoot their Foundry A2A issues.

## What's Included (Share These Files)

```
README.md                          Main guide - start here
├── QUICK_REFERENCE.md            Error lookup + quick fixes ⭐
├── A2A_TROUBLESHOOTING_GUIDE.md   Detailed troubleshooting steps
├── a2a_diagnostic.ps1            PowerShell diagnostic tool
└── a2a_validator.py              Python configuration validator
```

## Installation

1. Download or clone this repository
2. Read **README.md** first
3. Use the resources based on your error:
   - Error #1? → Open **QUICK_REFERENCE.md** → Error 1 section
   - Error #2? → Open **QUICK_REFERENCE.md** → Error 2 section

## Quick Start

**For Windows:**
```powershell
.\a2a_diagnostic.ps1 -Interactive
```

**For Linux/Mac with Python:**
```bash
python3 a2a_validator.py --interactive
```

## Support

If this package doesn't resolve your issue:
1. Collect the output from the diagnostic script
2. Review the detailed guide in **A2A_TROUBLESHOOTING_GUIDE.md**
3. Contact Azure Support with the diagnostic output

---

**Note:** This is a customer-facing troubleshooting package. Internal support documentation is not included.
