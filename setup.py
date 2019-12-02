#!/usr/bin/env python

from setuptools import setup

package_name = 'smarthive'
filename = package_name + '.py'

def get_long_description():
    try:
        with open('README.md', 'r') as f:
            return f.read();
    except IOError:
        return ''

setup (
    name=package_name,
    version='0.0.18',
    author='SmartHive Automation',
    author_email='dev@smarthive.ai',
    description='SmartHive Cloud Controller',
    url='https://www.smarthive.ai',
    long_description=get_long_description(),
    py_modules=[package_name],
    entry_points={
        'console_scripts': [
            'smarthive = smarthive:main'
        ]
    },
    license='Proprietary',
)
