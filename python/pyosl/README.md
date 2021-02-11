# OSL to GLSL converter

OSL to GLSL converter written in Python.

This library is an open-sourced component of [Verge3D](https://www.soft8soft.com/verge3d/) toolkit.

## Usage

pyosl includes a command line utility called osl2glsl.py. The command

```
  python osl2glsl your_shader.osl
```

will print converted GLSL shader to stdout. Use the:

```
  python osl2glsl your_shader.osl > your_shader.glsl
```

command to write GLSL shader to the file named `your_shader.glsl`.

## OSL standard library functions

Converter will try to use the built-in GLSL functions where possible. In all other cases it will rename OSL functions as follows:

* noise -> oslNoise
* transform -> oslTransform

It's up to you to write implementations of such oslNAME methods.

## Support
Got questions/found bugs? Ask on the [Verge3D Forums](https://www.soft8soft.com/forums/).

## License
This tool is licensed under the terms of the MIT license.
