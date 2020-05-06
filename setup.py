from setuptools import setup


def load_content(filename):
    with open(filename, "r", encoding="utf-8") as fp:
        return fp.read()


setup(
    name="discord-system-observer-bot",
    version="0.0.5",
    license="MIT License",
    author="Erik Körner",
    author_email="koerner@informatik.uni-leipzig.de",
    description="A Discord bot that observes a local machine, issues warnings and can be queries from Discord chat.",
    long_description=load_content("README.rst"),
    long_description_content_type="text/x-rst",
    url="https://github.com/Querela/discord-system-observer-bot",
    keywords=["discord", "bot", "system-observer"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Utilities",
    ],
    packages=["discord_system_observer_bot"],
    python_requires=">=3.6",
    install_requires=["discord.py", "psutil"],
    extras_require={
        "gpu": ["gputil"],
        "plot": ["matplotlib"],
        "dev": ["black", "pylint", "wheel", "twine"],
        "doc": ["pdoc3"],
    },
    entry_points={
        "console_scripts": ["dbot-observe = discord_system_observer_bot.cli:main"]
    },
)
