# Python
from copy import deepcopy
import os
import shutil
import shlex
import subprocess
import sys

# 3rd-party
import jinja2
import yaml


#TEMPLATES_ROOT = os.path.abspath(os.path.dirname(__file__))
CONFIG_FILE_PATH = "config.yml"


def ensure_file_directory_exists(file_path):
    """
    Create file's base directory if it does not exist.
    """
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

def run(command, shell=False):

    print("run command: %s" % command)
    #p = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell)
    p = subprocess.Popen(shlex.split(command), stdout=sys.stdout, stderr=sys.stderr, shell=shell)
    while True:
        # print one output char at a time
        #output_line = p.stderr.read(1).decode('utf8')
        #if output_line != "":
        #    print(output_line, end="")
        #else:
        # check if process finished
        return_code = p.poll()
        if return_code is not None:
            if return_code > 0:
                raise Exception("Command %s failed" % command)
            break
        else:
            import time
            time.sleep(1)

    return return_code


class TemplateRenderer:
    instance = None

    @classmethod
    def instance(cls, template_root_dir, config):
        if cls.instance is None or cls.instance.config != config:
            # Load template root: required to be able to use
            # {% include .. %} directives
            cls.instance = cls(template_root_dir, config)
        return cls.instance

    def __init__(self, template_root_dir, config):
        self.config = deepcopy(config)
        self.template_root_dir = template_root_dir

        # Create Jinja2 environment
        jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_root_dir),
            undefined=jinja2.StrictUndefined,
        )
        self.jinja_env = jinja_env

    def render_str(self, text):
        """
        Render a string

        @returns:
          str: rendered template string
        """
        template = self.jinja_env.from_string(text)
        return template.render(i**self.config)

    def render_file(self, path):
        """
        Render a template file.

        @returns:
          str: rendered template file content
        """
        try:
            template = self.jinja_env.get_template(path)
        except Exception:
            print("Error loading template " + path)
            raise
        print("render_file, config %s" % self.config)
        try:
            return template.render(**self.config)
        except (jinja2.exceptions.TemplateError, jinja2.exceptions.UndefinedError):
            print("Error rendering template " + path)
            raise
        except Exception:
            print("Unknown error rendering template " + path)
            raise


def render_templates(root_dir, config):
    """
    Render templates
    """
    renderer = TemplateRenderer(root_dir, config)
    TEMPLATES_FILENAMES = [
        "docker-compose.yml",
        "docker-compose-host.yml",
        "docker-compose-themes.yml"
    ]
    for filename in TEMPLATES_FILENAMES:
        rendered = renderer.render_file("%s.template" % filename)
        #dest_path = template_path.join(template_path.split(".")[:-1], ".")
        dest_path = os.path.join(os.path.abspath(root_dir), filename)
        write_to_file(rendered, dest_path)

    print("Templates generated")


def write_to_file(string, file_path):
    """
    Write text string to a file
    """
    ensure_file_directory_exists(file_path)
    print("output file path: %s" % file_path)
    with open(file_path, "w") as f:
        f.write(string)


def create_devstack(update_docker_images=False, destroy_old_devstack=True, update_git_repos=True):

    # check if Docker compose is installed
    if shutil.which("docker-compose") is None:
        raise Exception(
            "docker-compose is not installed. Please follow instructions from https://docs.docker.com/compose/install/"
        )

    # open config file
    with open(CONFIG_FILE_PATH) as f:
        config = yaml.safe_load(f)
    #print("config: %s" % config)

    # set git repositories directory
    os.environ["DEVSTACK_WORKSPACE"] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    # set openEDX version we want to build 
    os.environ["OPENEDX_RELEASE"] = config["OPENEDX_RELEASE"]
    # set -f params passed on to docker-compose
    os.environ["DOCKER_COMPOSE_FILES"] = "-f docker-compose.yml -f docker-compose-host.yml -f docker-compose-themes.yml"
    # increase docker-compose timeout
    os.environ["COMPOSE_HTTP_TIMEOUT"] = "180"

    # update Docker base images used by docker-compose if needed
    if update_docker_images:
        run("docker-compose pull", shell=False)

    # delete any existing Docker devstack
    # must be run before rendering templates
    if destroy_old_devstack:
        #run("./destroy.sh")
        run("docker-compose -f docker-compose.yml -f docker-compose-watchers.yml -f docker-compose-host.yml -f docker-compose-themes.yml down -v")

    # render docker-compose templates
    render_templates(".", config)

    # download/update git repositories
    if update_git_repos:
        # delete old package-json.lock files from previous NPM installations which cause an error when
        # updating git repositories
        run("sudo find . -iname package-json.lock -delete")
        run("sudo -E ./repo.sh clone_ssh")

    # provision
    services_to_install = ["lms"]  # LMS/Studio are always installed
    provision_sh_script_services = {
        # key is name used in provision.sh, value is name used in ACTIVATE_ variables in config file
        "ecommerce": ["ECOMMERCE"],
        "discovery": ["DISCOVERY"],
        "credentials": ["CREDENTIALS"],
        "e2e": ["CHROME", "FIREFOX"],
        "forum": ["FORUM"],
        "notes": ["NOTES"],
        "registrar": ["REGISTRAR"]
    }
    for sh_script_service, services in provision_sh_script_services.items():
        for s in services:
            if config["ACTIVATE_%s" % s]:
                services_to_install.append(sh_script_service)
                break
    cmd = "./provision.sh %s" % " ".join(services_to_install)
    run(cmd)


create_devstack(update_docker_images=False, destroy_old_devstack=True, update_git_repos=True)
