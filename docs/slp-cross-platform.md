# SLP discovery: Windows and Linux validation

SNF's SLP adapter delegates SLP wire behavior to the system-installed OpenSLP
`slptool` executable. It does not implement an SLP client or ship binaries.
Discovery is experimental until validated with an actual SLP responder on both
Windows and Linux. See RFC 2608 for SLPv2 semantics.

## Native Windows (first acceptance target)

Install a trusted OpenSLP distribution that includes a native Windows
`slptool.exe`. Add its directory to `PATH` or pass its absolute path via
`SLPPlugin(command=...)`. Availability of a compatible Windows binary is
**not yet verified**.

From PowerShell:

```powershell
Get-Command slptool.exe -ErrorAction SilentlyContinue
slptool.exe findsrvtypes
python -m pytest tests/test_slp.py tests/test_slp_subprocess.py tests/test_slp_lifecycle.py -q
```

## Linux / WSL2 (second acceptance target)

Install a distribution-provided OpenSLP `slptool` package, if available.
Package availability varies by distribution and release.

```bash
command -v slptool
slptool findsrvtypes
python -m pytest tests/test_slp.py tests/test_slp_subprocess.py tests/test_slp_lifecycle.py -q
```

WSL2 NAT/multicast restrictions can prevent discovery of LAN devices.
Successful mocked tests do **not** establish end-to-end network compatibility.

## Real binary acceptance test (both environments)

Run `slptool findsrvtypes` and `slptool findsrvs service:<type>` against
a **controlled SLP responder** registered in the same scope. Confirm that the
returned URL is visible through SNF as an `slp` observation. Repeat after
withdrawing and restoring the service; expect ADDED, REMOVED, ADDED.
No response from `findsrvtypes` can mean no reachable SLP services, not
necessarily a broken executable.

The adapter treats a successful complete poll as the current snapshot of
configured service types. A service absent from a later successful poll is
reported as removed. Failed polls do not intentionally synthesize removals.
If a service disappears transiently because of packet loss or responder delay,
the adapter may emit a removal and subsequent addition. This is a limitation
of polling-based discovery, not a verified device-disconnect signal.

## Runtime usage

```python
from snf.adapters.slp import SLPPlugin

plugin = SLPPlugin(
    service_types=["service:printer"],
    interval=60.0,
    command_timeout=15.0,
    # command=r"C:\path\to\slptool.exe",  # Windows if not on PATH
)
```

SLP support requires an executable on the host; no custom Python SLP
implementation or additional SLP Python dependency is introduced.
