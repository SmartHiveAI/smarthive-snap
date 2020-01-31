#!/usr/bin/env python3
''' Smarthive Setup file '''

from setuptools import setup

PACKAGE_NAME = 'smarthive'


def get_long_description():
    """Get Package long description"""
    try:
        with open('README.md', 'r') as f:
            return f.read()
    except IOError:
        return ''


setup(
    name=PACKAGE_NAME,
    version='0.0.24',
    author='SmartHive Automation',
    author_email='dev@smarthive.ai',
    description='SmartHive Cloud Controller',
    url='https://www.smarthive.ai',
    long_description=get_long_description(),
    py_modules=[PACKAGE_NAME],
    entry_points={'console_scripts': ['smarthive = smarthive:main']},
    license='Proprietary',
)
