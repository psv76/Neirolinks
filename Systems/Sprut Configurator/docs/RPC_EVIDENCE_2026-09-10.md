# Sprut WebUI RPC evidence — 2026-09-10

Source: real outgoing WebSocket messages captured by the operator on object work for Issue #22.

Only sanitized `params` are retained. Session `token`, `cid` and hub session `serial` are intentionally excluded.

## Service.visible

Action: hide Service tile from desktop.

```json
{"service":{"update":{"aId":118,"sId":13,"visible":false}}}
```

Confirmed method family:

```text
service.update
```

## Characteristic.statusVisible

Action: disable Characteristic in room status line.

```json
{"characteristic":{"update":{"aId":118,"sId":13,"cId":15,"statusVisible":false}}}
```

Confirmed method family:

```text
characteristic.update
```

## Alice / Yandex bridge removal

Action: disable Service in Alice bridge.

```json
{"bridgeService":{"delete":{"bridgeIndex":"Yandex_1","aId":118,"sId":13}}}
```

Confirmed facts:

- bridge family is `bridgeService`;
- disable operation is `delete`;
- current bridge index is `Yandex_1`;
- membership is addressed by `aId + sId`.

Not yet confirmed:

- enable/create operation;
- read/list operation used to determine current membership for DRY RUN and VERIFY.
