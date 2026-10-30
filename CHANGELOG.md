# Changelog

## [0.2.0](https://github.com/phileaton/ha-charge-wise/compare/v0.1.0...v0.2.0) (2026-10-30)


### ⚠ BREAKING CHANGES

* the mode select is removed; use the Charging enabled, Solar charging, Off-peak charging and Manual override switches instead
* the mode select is removed; use the Charging enabled, Solar charging, Off-peak charging and Manual override switches instead

### Features

* add project plan for ChargeWise integration ([643ab3b](https://github.com/phileaton/ha-charge-wise/commit/643ab3bb78c1996ea30859e54bf59a9a30e0a98b))
* **binary_sensor:** remove stale entity when battery sensor is removed ([a483343](https://github.com/phileaton/ha-charge-wise/commit/a48334325df51c3f5e5a726fa4b1dbb2e9d9c360))
* **config-flow, coordinator:** replace house power with solar power ([1fe190f](https://github.com/phileaton/ha-charge-wise/commit/1fe190f7bc78959f164a7050b0dc97960567b7ba))
* **config-flow, options-flow:** add  back functionality to config flows ([5bfbe6e](https://github.com/phileaton/ha-charge-wise/commit/5bfbe6e6a0e8dc21e25dc0d9962906b5570d82e0))
* **config-flow:** implement multi-page configuration for Charge Wise ([5d22733](https://github.com/phileaton/ha-charge-wise/commit/5d22733a1de04e5b1f6ff8e0e1a411b1741d921e))
* **coordinator, number:** add maximum current property ([ad581db](https://github.com/phileaton/ha-charge-wise/commit/ad581db77aae623153ea5e3d132e2d8ee86e9c5e))
* **ev-first:** add EV-first charging functionality ([e114555](https://github.com/phileaton/ha-charge-wise/commit/e1145558190b5f4f32c1ff06b3466d1273fb86cb))
* **house-load:** add house load profile for learned consumption ([2ecfffd](https://github.com/phileaton/ha-charge-wise/commit/2ecfffd021b7f4ab046eeb23f862924a13080cde))
* implement Charge Wise configuration and control features ([5b7786e](https://github.com/phileaton/ha-charge-wise/commit/5b7786e955d2a9014f98d567ca31aa52fa026a83))
* replace mode select with source switches and off-peak windows ([ee33fd9](https://github.com/phileaton/ha-charge-wise/commit/ee33fd910ede0c42003905ae1c0ad8f105b06725))
* replace mode select with source switches and off-peak windows ([a80b4ee](https://github.com/phileaton/ha-charge-wise/commit/a80b4eee0e03a06790e58879d395fc6f30681ba6))
