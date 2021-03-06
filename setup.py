from setuptools import setup

setup(name              = 'Wirecamel',
      description       = 'Python based project that automate the use of SSLSPlit and generate human readable reports',
      author            = 'Hamza ESSAYEGH',
      author_email      = 'hamza.essayegh@protonmail.com',
      maintainer        = 'Hamza ESSAYEGH',
      maintainer_email  = 'hamza.essayegh@protonmail.com',
      url               = 'https://github.com/Querdos/wirecamel',
      platform          = 'Linux',
      version           = '1.0',
      packages          = ['wirecamel', 'wirecamel/lib'],
      data_files        = [
          (
              '/root/.wirecamel/conf',
              [
                  'wirecamel/conf/hostapd.yaml',
                  'wirecamel/conf/iptables-configuration',
                  'wirecamel/conf/packages.yaml'
              ])
      ],
      install_requires  = [
          'iso8601',
          'tabulate',
          'python-dateutil',
          'pyyaml'
      ],
      entry_points      = {
          'console_scripts': [
              'wirecamel = wirecamel.wirecamel:main'
          ]
      },
      classifiers       = [
          'Development Status :: 4 - Beta',
          'Environment :: Console',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: Developers',
          'Operating System :: Linux :: Debian',
          'Programming Language :: Python',
      ]
)
