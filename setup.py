import setuptools

if __name__ == "__main__":

    with open('requirements.txt', 'r') as f:
        requirements = f.readlines()
        requirements = [line.strip() for line in requirements if line.strip()]

    setuptools.setup(name = 'nanonis_control',
    version = '1.0.1',
    author = 'Dillon Wong',
    author_email = '',
    description = 'Control Nanonis with Python instead of LabView!',
    url = 'https://github.com/dilwong/nanonis_control',
    install_requires = requirements,
    packages=['nanonis_control'],
    )