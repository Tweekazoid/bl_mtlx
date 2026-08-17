# MaterialX Import/Export for Blender

A professional-grade Blender addon for **bidirectional** conversion between Blender materials and the MaterialX (`.mtlx`) format — export Blender shader graphs to MaterialX **and** import MaterialX documents back into Blender node trees, with round-trip fidelity, comprehensive node support, and validation.

> This project began as a fork of [bhouston/blender_materialx_addon](https://github.com/bhouston/blender_materialx_addon) and has since grown into a standalone project with substantially expanded capabilities (full import support, procedural-texture round-tripping, and improved node fidelity). See [Acknowledgments](#-acknowledgments).

## 🚀 Features

- **Bidirectional Conversion**: Export Blender materials to MaterialX **and** import MaterialX files back into Blender node graphs
- **Round-Trip Fidelity**: Export → import reconstructs the original shader graph, including procedural texture chains
- **MaterialX 1.39 Compliance**: Full compliance with the latest MaterialX specification
- **Comprehensive Node Support**: Principled BSDF, image/procedural textures, math/vector operations, color utilities, and more
- **Procedural Texture Support**: Voronoi, noise, wave, brick, checker, gradient and Color Ramp nodes map to and from MaterialX procedural nodes
- **Blender Addon UI**: Export single or all materials, and import `.mtlx` files, directly from the UI
- **Command-Line Export**: Export materials from any `.blend` file without opening Blender
- **Texture Export**: Export and copy textures with relative/absolute path support
- **Advanced Validation**: Built-in MaterialX document validation with detailed error reporting
- **Performance Monitoring**: Real-time performance tracking and optimization
- **Configuration Panel**: In-UI configuration for export settings

![Blender UI](BlenderScreenshot.png)

## 📦 Installation

### Install as a Blender Extension (recommended)

This addon ships as a Blender Extension (`blender_manifest.toml`). Install the `src/` folder as an add-on:

1. Copy the `src/` directory into your Blender extensions/add-ons directory and rename it to `material_x`:

   - **Windows**: `%APPDATA%\Blender Foundation\Blender\VERSION\extensions\user_default\`
   - **macOS**: `~/Library/Application Support/Blender/VERSION/extensions/user_default/`
   - **Linux**: `~/.config/blender/VERSION/extensions/user_default/`

2. Enable the addon in Blender: `Edit > Preferences > Add-ons`, then search for **"MaterialX"**.

### Development Installation

```bash
python3 dev_upgrade_addon.py
```

**Important**: Run this script after making code changes to deploy updates to Blender.

## 🎮 Usage

### In Blender

- Access the MaterialX panel in `Properties > Material > MaterialX`
- **Export** the selected material or all materials to `.mtlx`
- **Import** a `.mtlx` file to rebuild it as a Blender node graph
- Configure export settings in the Configuration panel
- View real-time export status and performance metrics

### Command-Line

```bash
python cmdline_export.py <blend_file> <material_name> <output_mtlx_file> [options]
```

**Options:**

- `--export-textures` : Export texture files
- `--texture-path PATH` : Directory to export textures to
- `--version VERSION` : MaterialX version (default: 1.39)
- `--relative-paths` : Use relative paths for textures
- `--copy-textures` : Copy texture files

## 🧩 Supported Node Types

Node mappings work in **both directions** (export to MaterialX and import back to Blender) unless noted.

### Core Material Nodes

- **Principled BSDF** ↔ `standard_surface` (with full parameter support)
- **Image Texture** ↔ `image` (with texture coordinate support)
- **Texture Coordinate** ↔ `texcoord` (with multiple coordinate types)

### Math and Color Nodes

- **RGB, Value** ↔ `constant` (color3/float)
- **Math, Vector Math** ↔ `math`, `vector_math` (with all operations)
- **Mix** ↔ `mix` (with proper parameter mapping)
- **Map Range** ↔ `range` / `remap`
- **Invert, Separate/Combine Color** ↔ `invert`, `separate3`, `combine3`
- **Color Ramp** ↔ `ramplr` / ramp nodes (color stops reconstructed on import)

### Texture Nodes

- **Voronoi Texture** ↔ `worleynoise3d` / `cellnoise3d` (Distance and Color outputs, scale baked into position)
- **Noise, Wave** ↔ `noise2d`, `wave`
- **Checker, Gradient** ↔ `checkerboard`, `ramplr`
- **Brick Texture** ↔ `brick` (with mortar and brick pattern support)
- **Musgrave Texture** → `musgrave` (fractal noise texture)

### Utility Nodes

- **Normal Map, Bump** ↔ `normalmap`, `bump`
- **Mapping, Layer, Add, Multiply** ↔ `place2d` / `UsdTransform2d`, `layer`, `add`, `multiply`
- **HSV/RGB conversion** ↔ `hsvtorgb`, `rgbtohsv`
- **Geometry Info** → `position` (position, normal, tangent data)
- **Object Info** → `constant` (object-specific data)
- **Light Path** → `constant` (light path information)

## 📊 Export Results

The exporter returns comprehensive results including:

- Export success status and error messages
- List of unsupported nodes with helpful suggestions
- Performance metrics and optimization suggestions
- MaterialX validation results
- File output path and optimization status

## 🧪 Testing

Run the comprehensive test suite:

```bash
python3 test_blender_addon.py
```

This tests:

- Addon installation and UI functionality
- Export of real-world material examples
- Round-trip import validation
- MaterialX file validation
- Error handling for unsupported nodes
- Performance testing

See [TESTING.md](TESTING.md) for detailed test results and analysis.

## 🔧 Development

For development setup, testing, and contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

Project home: [github.com/Tweekazoid/bl_mtlx](https://github.com/Tweekazoid/bl_mtlx)

## 📋 Requirements

- **Blender**: 4.0 or higher (developed and tested on Blender 5.x)
- **No external dependencies** (uses the included MaterialX library)

## 📄 License

See [LICENSE](LICENSE).

## 🙏 Acknowledgments

- **Ben Houston** ([bhouston/blender_materialx_addon](https://github.com/bhouston/blender_materialx_addon)): For the original addon that inspired this project and served as the starting point.
- **MaterialX Team**: For the excellent MaterialX specification and library.
- **Blender Foundation**: For the powerful Blender platform.
- **kwokcb** ([MaterialX_Learn](https://github.com/kwokcb/MaterialX_Learn)): For the bundled `mtlxutils` MaterialX helper utilities.
