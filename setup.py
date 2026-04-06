from setuptools import setup

APP = ['launch_app.py']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'assets/AppIcon.icns',
    'plist': {
        'CFBundleName': 'Audio Transkript',
        'CFBundleDisplayName': 'Audio Transkript',
        'CFBundleIdentifier': 'com.matze.audio-transkript',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'LSUIElement': True,
        'NSMicrophoneUsageDescription': 'Audio Transkript benoetigt Zugriff auf das Mikrofon.',
        'NSAppleEventsUsageDescription': 'Audio Transkript benoetigt Zugriff auf Bedienungshilfen.',
    },
}

setup(
    app=APP,
    install_requires=[],
    options={'py2app': OPTIONS},
)
