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

You can also adjust some behaviours in the integration’s Options Flow:
- the polling interval in hours, from 3 to 24 hours
- if update entity use or not the unstable versions

## 🧰 Services

### my_custom_manager.get_customs_list

Download the list of custom_component managed by the repository.

| Field        | Description                           | Required |
|--------------|---------------------------------------|----------|
| config_entry | Select the configured instance to use | ✅       |

The returned data is a dictionary with name and description:
```yaml
my_custom_manager: My Custom Component Version Manager
another_custom: Another beautiful custom component for HomeAssistant
```

### my_custom_manager.get_supported_versions

Fetch the list of available versions for specific custom component.

Fields:
| Field         | Description                                  | Required   |
|---------------|----------------------------------------------|------------|
| config_entry  | Select the configured instance to use        | ✅         |
| component     | Name of the component to download            | ✅         |
| show_unstable | Return also ustable versions (alpha,beta,rc) | ❌ (False) |

The returned data is a list of available versions:
```yaml
supported_versions:
  - 2.0.0
  - 1.0.0
```

### my_custom_manager.download_custom

Download and install a custom component from the configured base URL. This service installs any supported version, whether stable or unstable, regardless of the configuration of the option in the entry.

Fields:
| Field        | Description                           | Required |
|--------------|---------------------------------------|----------|
| config_entry | Select the configured instance to use | ✅       |
| component    | Name of the component to download     | ✅       |
| version      | Version to install                    | ❌       |

## 🪣 Repository

This repository stores metadata for multiple integration projects.
It contains a global repository index and one folder for each project.

### 📁 Repository Structure

```
├── repository.json
└── customs
    ├── my_custom_manager
    |   ├── custom.json
    |   └── 1.0.0.zip
    ├── another_custom
    |   └── custom.json
```

### 📄 repository.json

This file contains:

- **name**: name of the repository project
- **description**: a longest description
- **homepage**: the home-page of the repository
- **customs**: the list of hosted custom components, with custom domain as key and name

Example:
```json
{
  "name": "Fantastic customs",
  "description": "Collection of awesome secret integrations and components",
  "customs": {
    "my_custom_manager": "My Custom Component Version Manager",
    "another_custom": "Another custom project"
  }
}
```

### 📄 custom.json (inside each project folder)

This file is inside a folder with name same of projects key. Contains all metadata specific to a project:
- **name**: of the project
- **description**: a longest project description
- **homepage**: the home-page of the project
- **changelog**: the URL of project changelod in MarkDown format
- **versions**: dictionary with list of all available versions.

Each version uses the version number as its key, and contains all information to describe the version:
- **ha_min**: the minimum version of Home Assistant
- **ha_max**: (optional) the latest version compatible with this custom version
- **release_file**: url for custom download. The file is a zip file with this structure inide `custom_component/<custom_name>/*`.
- **homepage**: (optional) url for version release page, usefull for present the release

Example:
```json
{
  "name": "My Custom Component Version Manager",
  "description": "Custom component inspired to HACS to manage some personal customs not published on github.",
  "homepage": "https://git.villavasco.ovh/home-assistant/my_custom_manager/",
  "changelog": "https://git.villavasco.ovh/home-assistant/my-custom-manager/raw/branch/main/CHANGELOG.md",
  "versions": {
    "1.0.0": {
      "ha_min": "2025.11.0",
      "release_file": "https://git.villavasco.ovh/home-assistant/my-custom-manager/releases/download/v1.0.0/my-custom-manager.zip",
      "homepage": "https://git.villavasco.ovh/home-assistant/my-custom-manager/releases/tag/v1.0.0"
    }
  }
}
```

## 🤝 Contributing

Contributions are always welcome!
If you’d like to improve this project, please read the [Contribution Guidelines](CONTRIBUTING.md)

## 🪪 License

This project is licensed under the terms of the [MIT License](LICENSE).

---

[license-shield]: https://img.shields.io/badge/MIT-LICENSE?style=for-the-badge&label=LICENSE
[my-button]: https://my.home-assistant.io/redirect/integration/?domain=my_custom_manager