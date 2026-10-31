# `device_capability`

One reported capability of a device: WebXR, plane detection, GPU class, and so on.

## Fields

| Field | Type | Notes |
| id | PK | |
| device | FK → [device](device.md) | |
| capability | text | Capability key, shared vocabulary with scene requirements |
| detail | text, nullable | e.g. GPU tier, OS version |
| reported_at | timestamp | |

## Relationships

- Belongs to [device](device.md); matched against [scene requirements](scene_requirement.md)
