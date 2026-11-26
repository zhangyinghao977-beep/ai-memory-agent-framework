# Hongchenxian: base prototype and the first three DLCs

[简体中文](DLC.zh.md) · [Base demo and architecture](README.md) · [Stage 5 / DLC 04: from agent to AI architecture](STAGE5.en.md)

This is the four-stage prototype of the independent agent. The first three extensions share its base code but run independently; they are not an integrated deployment.

From this directory, run `python demo.py`. Python 3.10+ and its standard library are enough. No model, API key, private recordings or network service is required.

| Extension | Design and reproducible behavior | Run from this directory |
| --- | --- | --- |
| **01 · Locally reconstructed knowledge and patches** | Keep the long-term original. Reconstruct selected fragments into an isolated short-term working copy. Edit there first, then explicitly merge against the shared base; leave conflicts open and preserve the original. | `python dlc01/short_memory.py` |
| **02 · Index graphs** | Map keywords to accessible views. Commercial agents follow the map they are allowed to see, not the underlying knowledge tree or single trusted source. The demo gateway reads only authorized projections; revocation closes the existing route. | `python dlc02/index_map.py` |
| **03 · Event chains, FSM protocols, and reflexes** | Concrete keys identify a versioned process and its slices. Abstract keys group reusable candidates. A reflex starts the same FSM protocol, which checks current conditions and waits for fresh evidence. | `python dlc03/protocol.py` |

To see reconstruction without a working-copy merge, run `python dlc01/rebuild.py --query 周四`. Run `python -m unittest -v` inside each extension directory, and separately here for the base tests.

**Evidence boundary.** The inputs, role assignments and actuators are synthetic. DLC 02 uses SQLite indexed key lookup; it has not been shown to beat an inverted index. Its demo assumes trusted identity binding and filesystem separation outside the gateway, and cannot revoke copies that were already read. DLC 03 keeps reflex bindings and live execution state in process. DLC 04 and Stage 5 are research designs, not runnable parts of this delivery.
