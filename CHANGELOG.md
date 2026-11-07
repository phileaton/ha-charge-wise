# Changelog

## [0.2.0](https://github.com/phileaton/ha-charge-wise/compare/v0.1.0...v0.2.0) (2026-11-07)


### ⚠ BREAKING CHANGES

* the mode select is removed; use the Charging enabled, Solar charging, Off-peak charging and Manual override switches instead
* the mode select is removed; use the Charging enabled, Solar charging, Off-peak charging and Manual override switches instead

### Features

* add forecast accuracy tracking and related configurations ([4ac9adb](https://github.com/phileaton/ha-charge-wise/commit/4ac9adb4a6e0ff8edb0d94cb3ec2bb0d07142dee))
* add project plan for ChargeWise integration ([643ab3b](https://github.com/phileaton/ha-charge-wise/commit/643ab3bb78c1996ea30859e54bf59a9a30e0a98b))
* **binary_sensor:** add vehicle connected and charging sensors ([343376b](https://github.com/phileaton/ha-charge-wise/commit/343376bd70456760d4115ca216cd97572e465d41))
* **binary_sensor:** remove stale entity when battery sensor is removed ([a483343](https://github.com/phileaton/ha-charge-wise/commit/a48334325df51c3f5e5a726fa4b1dbb2e9d9c360))
* **brand:** add 2x icon and logo and enable brand validation ([1907d4b](https://github.com/phileaton/ha-charge-wise/commit/1907d4b60ba6b0272b76325c12e0655d70e104a4))
* **config-flow, coordinator:** replace house power with solar power ([1fe190f](https://github.com/phileaton/ha-charge-wise/commit/1fe190f7bc78959f164a7050b0dc97960567b7ba))
* **config-flow, options-flow:** add  back functionality to config flows ([5bfbe6e](https://github.com/phileaton/ha-charge-wise/commit/5bfbe6e6a0e8dc21e25dc0d9962906b5570d82e0))
* **config-flow:** implement multi-page configuration for Charge Wise ([5d22733](https://github.com/phileaton/ha-charge-wise/commit/5d22733a1de04e5b1f6ff8e0e1a411b1741d921e))
* **config-flow:** support OCPP status sensor for EV detection ([b07403f](https://github.com/phileaton/ha-charge-wise/commit/b07403fd0c098d112cb3d3a0be874b59891af5de))
* **config:** add settle hold and smoothing window configuration options ([a6574f7](https://github.com/phileaton/ha-charge-wise/commit/a6574f7667d3db02ccf57e7c1b3daf027d6fcc83))
* **controller:** add battery growth tracking for discharge spikes ([a625e5b](https://github.com/phileaton/ha-charge-wise/commit/a625e5b18b0e3e540b5b7175ee5ee39c4e4e25ae))
* **coordinator, number:** add maximum current property ([ad581db](https://github.com/phileaton/ha-charge-wise/commit/ad581db77aae623153ea5e3d132e2d8ee86e9c5e))
* **coordinator:** implement EV-first hold state restoration ([87edcf1](https://github.com/phileaton/ha-charge-wise/commit/87edcf15e86cc8bb512ae2098a3c3387f67b668f))
* **coordinator:** implement switch command grace period ([e525aec](https://github.com/phileaton/ha-charge-wise/commit/e525aecc872b0cedea5dad1b9994bc5fb800e659))
* **coordinator:** log charger decision changes for better debugging ([cea9c8d](https://github.com/phileaton/ha-charge-wise/commit/cea9c8d287e00dcfdaaf4b8c6f8d095631ac6d6b))
* **dashboard:** add dashboard creation and removal functionality ([2d659b8](https://github.com/phileaton/ha-charge-wise/commit/2d659b8ba1f3e3fb87d37da188db3f34647e9b48))
* **dashboard:** add solar metrics to forecast section ([a276500](https://github.com/phileaton/ha-charge-wise/commit/a276500ddde4ab06af8dd31f8dab419082836974))
* **dashboard:** compare solar forecast with actual ([c201e9f](https://github.com/phileaton/ha-charge-wise/commit/c201e9f9fdc8e3da3dcc3070b6698099705367f8))
* **dashboard:** enhance dashboard layout and functionality ([c5935e4](https://github.com/phileaton/ha-charge-wise/commit/c5935e45f10f15c5c7c41e8103b0208272abe10b))
* **dashboard:** enhance dashboard with new metrics and layout ([48ee903](https://github.com/phileaton/ha-charge-wise/commit/48ee903e291c905b352798b196394912b43252d7))
* **dashboard:** enhance solar forecast graph configuration ([8da476d](https://github.com/phileaton/ha-charge-wise/commit/8da476dfe9c915e4e3b998d319900141187a1698))
* **dashboard:** update Garage Charger dashboard entities ([093e98c](https://github.com/phileaton/ha-charge-wise/commit/093e98cd7a8f70461cb1936273a1fb6131a5ea7e))
* **devcontainer:** add additional appPort configuration f ([c9cd7ae](https://github.com/phileaton/ha-charge-wise/commit/c9cd7ae234f83547421e0d011698df5af6529b91))
* **devcontainer:** add appPort configuration for container ([74586fe](https://github.com/phileaton/ha-charge-wise/commit/74586fe35d11f0127356cb84b863e1116df5555f))
* **ev-first:** accumulate EV-first energy usage and adjust surplus ([3835821](https://github.com/phileaton/ha-charge-wise/commit/383582163654d1ee5b1a24a155ba26b0cb82b335))
* **ev-first:** add EV-first charging functionality ([e114555](https://github.com/phileaton/ha-charge-wise/commit/e1145558190b5f4f32c1ff06b3466d1273fb86cb))
* **ev-first:** add release margin configuration and logic ([9bafe48](https://github.com/phileaton/ha-charge-wise/commit/9bafe485719b5628eb1f495b8abdd2799e1935cc))
* **ev-first:** update release margin pct and adjust related logic ([6de2c1d](https://github.com/phileaton/ha-charge-wise/commit/6de2c1d9541b1531f35a66431a6ea56ccb66139f))
* **forecast_accuracy:** enhance tracking of forecast accuracy ([4035df1](https://github.com/phileaton/ha-charge-wise/commit/4035df13eea2da74bb5456fd5924e7ccd6aaf703))
* **house-load:** add house load profile for learned consumption ([2ecfffd](https://github.com/phileaton/ha-charge-wise/commit/2ecfffd021b7f4ab046eeb23f862924a13080cde))
* implement Charge Wise configuration and control features ([5b7786e](https://github.com/phileaton/ha-charge-wise/commit/5b7786e955d2a9014f98d567ca31aa52fa026a83))
* **number:** default manual and off-peak current to charger maximum ([af9839f](https://github.com/phileaton/ha-charge-wise/commit/af9839ffeeefbe4a893f82ffcf460df1e04c7cb6))
* replace mode select with source switches and off-peak windows ([ee33fd9](https://github.com/phileaton/ha-charge-wise/commit/ee33fd910ede0c42003905ae1c0ad8f105b06725))
* replace mode select with source switches and off-peak windows ([a80b4ee](https://github.com/phileaton/ha-charge-wise/commit/a80b4eee0e03a06790e58879d395fc6f30681ba6))
* **scenarios:** add export and replay functionality for energy readings ([16e0cbd](https://github.com/phileaton/ha-charge-wise/commit/16e0cbd8f8f188437947e09c62f851433556fefa))
* **sensor, dashboard:** update unit handling and add budget checks ([086bc13](https://github.com/phileaton/ha-charge-wise/commit/086bc135f6e8c0b53abdfeecfe34ed9b0cdd4123))
* **sensor:** add charger session sensor ([343376b](https://github.com/phileaton/ha-charge-wise/commit/343376bd70456760d4115ca216cd97572e465d41))
* **sensor:** show produced versus forecast energy on forecast accuracy ([ddb0f24](https://github.com/phileaton/ha-charge-wise/commit/ddb0f2462b61c7a0b9fee35496644e24877a9609))
* show production value in forecast graph legend ([7d499db](https://github.com/phileaton/ha-charge-wise/commit/7d499db13effaa67422bff7a88704bdceddecda4))
* **sweep:** add grid-search functionality for controller settings ([5f155cc](https://github.com/phileaton/ha-charge-wise/commit/5f155cc8ae1b4dd6836b11d2eff002bd793e1ed1))
* use forecast_remaining in chart legend for better readability ([e20e611](https://github.com/phileaton/ha-charge-wise/commit/e20e6119538b1582d520324201b39af843d5fe93))


### Bug Fixes

* **charger_status:** clarify OCPP Finishing status handling ([603831d](https://github.com/phileaton/ha-charge-wise/commit/603831da539f8ec2eb168e798b3fae5f9afb8fb9))
* **coordinator:** confirm solar start and skip unavailable current limit ([e58b090](https://github.com/phileaton/ha-charge-wise/commit/e58b09003ecd1cc9c91b3469f77e0604be30169e))
* **coordinator:** pause solar charging on forecast shortfall ([46eb8fe](https://github.com/phileaton/ha-charge-wise/commit/46eb8fe1f50c1ffa8b60c606bd41366864f4cd38))
* **coordinator:** prevent repeated battery protection reductions ([75599c4](https://github.com/phileaton/ha-charge-wise/commit/75599c489ee843a403e4318c0a528c856d47b0bf))
* correct battery-first charging and dashboard feedback ([e2bcb69](https://github.com/phileaton/ha-charge-wise/commit/e2bcb69463a0d7d7310362bf905c32393da5b37a))
* **forecast_accuracy:** improve state restoration logic ([92cb65d](https://github.com/phileaton/ha-charge-wise/commit/92cb65d467cd85913cbf5fd4ba215df8e4eef8a3))
* improve charger status handling ([343376b](https://github.com/phileaton/ha-charge-wise/commit/343376bd70456760d4115ca216cd97572e465d41))
* improve charging dashboard layout and clarity ([9c85aff](https://github.com/phileaton/ha-charge-wise/commit/9c85affa3492c263b75460a89b9b672f7956bfb7))
* **manifest, getting-started:** update integration type and description ([207adef](https://github.com/phileaton/ha-charge-wise/commit/207adef73a679e0ca5653ea3152b447a792b27cf))
* restore forecast graph by hiding non-meaningful legend value ([25ec925](https://github.com/phileaton/ha-charge-wise/commit/25ec925171d7e797e1822f0343c4c322121b9e3f))
* **sensor:** keep solar budget available when disabled ([9e1445b](https://github.com/phileaton/ha-charge-wise/commit/9e1445b547493e309628b1df4926bdf53d83cf7f))
