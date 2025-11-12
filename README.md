# 🧩 My Custom Component Version Manager

[![License][license-shield]](LICENSE)

A Home Assistant integration inspired by **HACS**, but without a web interface.
It’s a simple yet powerful tool to **manage**, **install**, and **update** custom integrations that are not hosted on GitHub.

## 🚀 Features

- 📦 Fetch and list all available custom integrations from a custom repository
- 🔄 Download and install selected integration
- 🧭 Automatic version checking
- 🧾 Displays changelogs directly from the changelog
- ⚙️ Uses Home Assistant’s Update Entity for component update

## 📥 Installation

1. Open your Home Assistant configuration directory (the one containing `configuration.yaml`).
2. If it doesn’t exist yet, create a folder called `custom_components`.
3. Inside that folder, create another folder named `my_custom_manager`.
4. Download all files from this repository’s `custom_components/my_custom_manager/` directory.
5. Copy those files into your newly created `custom_components/my_custom_manager/` folder.
6. Restart Home Assistant.

## ⚙️ Configuration

The integration is fully configured from the Home Assistant UI. In the HA UI, go to **Settings** → **Devices & Services** → **Integrations**, click “**+ Add Integration**”, and search for “**My Custom Manager**”.

[![Open your Home Assistant instance and show an integration.](https://my.home-assistant.io/badges/integration.svg)](my-button)

When adding the integration you need only to provide the Base URL of remote repository (e.g. https://example.com/my_customs/).

The integration will automatically:
1. Fetch the list of available custom components
2. Check the presence of already present custom_components managed by the remote repository
3. Create update entities for each component

You can also adjust the polling interval in the integration’s Options Flow.

## 🧰 Services

### my_custom_manager.download_list

Download the list of custom_component managed by the repository.

| Field        | Description                           | Required |
|--------------|---------------------------------------|----------|
| config_entry | Select the configured instance to use | ✅       |

The returned data is a dictionary with name and description:
```yaml
my_custom_manager: My Custom Component Version Manager
another_custom: Another beautiful custom component for HomeAssistant
```

### my_custom_manager.download_custom

Download and install a custom component from the configured base URL.

Fields:
| Field        | Description                           | Required |
|--------------|---------------------------------------|----------|
| config_entry | Select the configured instance to use | ✅       |
| component    | Name of the component to download     | ✅       |
| version      | Version to install                    | ❌       |

## 🤝 Contributing

Contributions are always welcome!
If you’d like to improve this project, please read the [Contribution Guidelines](CONTRIBUTING.md)

## 🪪 License

This project is licensed under the terms of the [MIT License](LICENSE).

---

[license-shield]: https://img.shields.io/badge/MIT-LICENSE?style=for-the-badge&label=LICENSE
[my-button]: https://my.home-assistant.io/redirect/integration/?domain=my_custom_manager