# Warus level/posegraph evidence

Source: `Worlds/w01_mangrove/b00_mangrove_seaLion.pak`.

## Ledge Guardian actor

The ROOM data contains a `Ledge Guardians` layer and two near-duplicate Ledge
Guardian actor/component groups. Both render components reference the Warus
Shield CHAR entry and select Pompy Idle:

```text
CHAR entry UUID: 02603871c3ab4ccfb81b27a7929bc20a
CHAR name:       Warus_Shield
SKEL UUID:       aa6cd44f133648f1ad79a9c0fab1e7d0
idle clip:       a_pompy_idle_ws
ANIM UUID:       610e7380b3f647c284ea16fbde80b2c0
```

Relevant binary/string offsets:

```text
0x430C4  Ledge Guardians
0x433C9  T.Ledge Guardian - Render
0x43416  a_pompy_idle_ws
0x43A8E  T.Ledge Guardian - ActorKeyframe
0x43C0E  a_pompy_idle_ws
0x43C30  a_pompy_attack_forward_ws
0x43C5D  a_pompy_jump_into_arena_ws

0x44C11  T.Ledge Guardian - Render (second copy)
0x44C5E  a_pompy_idle_ws
0x452D6  T.Ledge Guardian - ActorKeyframe (second copy)
0x45456  a_pompy_idle_ws
0x4547F  a_pompy_attack_forward_ws
0x454CF  a_pompy_jump_into_arena_ws
```

The actor group also contains Render, ActorCollision, SplineMotion,
RenderMethodResolver, TakeDamage, Health, blocking-wall, force/trigger and
SuperCombinedAbilityResponder components. Consequently the final GPU palette may
contain state and procedural contributions beyond the named normal clip.

## Implication for capture validation

`a_pompy_idle_ws` is the level-selected base clip for this actor. `b_idle_1_ws`
exists in the same Character resource but is not the correct reference for the
supplied Ledge Guardian captures.

Exact 1:1 reconstruction still requires the runtime state of the additional
actor components or a capture of their input pose. The base clip and its timing
are now identified independently of those remaining layers.
