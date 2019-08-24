"""hifipower setup, meant for Raspberry Pi or Orange Pi"""
from setuptools import setup

__version__ = '0.1a1'
__author__ = 'Christophe Catherine Slychan'
__author_email__ = 'krzysztof.slychan@gmail.com'
__github_url__ = 'http://github.com/elegantandrogyne/hifipower'
__dependencies__ = ['Flask >= 1.0.2']

with open('README.md', 'r') as readme_file:
    long_description = readme_file.read()

setup(name='hifipower', version=__version__,
      description='On/off control via web API for hi-fi audio equipment',
      long_description=long_description,
      url=__github_url__, author=__author__, author_email=__author_email__,
      license='MIT',
      packages=['hifipower'], include_package_data=False,
      classifiers=['Development Status :: 3 - Alpha',
                   'Topic :: System :: Hardware :: Hardware Drivers',
                   'License :: OSI Approved :: MIT License',
                   'Natural Language :: English',
                   'Operating System :: POSIX :: Linux',
                   'Programming Language :: Python :: 3 :: Only',
                   'Framework :: Flask'],
      install_requires=__dependencies__, zip_safe=True,
      entry_points={'console_scripts': ['hifipower = hifipower.main:main']}
      )

