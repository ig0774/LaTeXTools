from pdfBuilder import PdfBuilder
import sublime

import os
import re
import shlex
import sys

from string import Template

try:
	from latextools_utils.external_command import (
		external_command, get_texpath, update_env
	)
except:
	from LaTeXTools.latextools_utils.external_command import (
		external_command, get_texpath, update_env
	)

if sys.version_info < (3, 0):
	strbase = basestring
	from pipes import quote
else:
	strbase = str
	from shlex import quote

_ST3 = sublime.version() >= '3000'


#----------------------------------------------------------------
# ScriptBuilder class
#
# Launch a user-specified script
#
class ScriptBuilder(PdfBuilder):

	CONTAINS_VARIABLE = re.compile(
		r'\$(?:file|file_path|file_name|file_ext|file_base_name)\b',
		re.IGNORECASE | re.UNICODE
	)

	def __init__(self, tex_root, output, engine, options,
				 tex_directives, builder_settings, platform_settings):
		# Sets the file name parts, plus internal stuff
		super(ScriptBuilder, self).__init__(tex_root, output, engine, options,
			tex_directives, builder_settings, platform_settings)
		# Now do our own initialization: set our name
		self.name = "Script Builder"
		# Display output?
		self.display_log = builder_settings.get("display_log", False)
		plat = sublime.platform()
		self.cmd = builder_settings.get(plat, {}).get("script_commands", None)
		self.env = builder_settings.get(plat, {}).get("env", None)
		# Loaded here so it is calculated on the main thread
		self.texpath = get_texpath() or os.environ['PATH']

	# Very simple here: we yield a single command
	# Also add environment variables
	def commands(self):
		# Print greeting
		self.display("\n\nScriptBuilder: ")

		# create an environment to be used for all subprocesses
		# adds any settings from the `env` dict to the current
		# environment
		env = dict(os.environ)
		env['PATH'] = self.texpath
		if self.env is not None and isinstance(self.env, dict):
			update_env(env, self.env)

		if self.cmd is None:
			sublime.error_message(
				"You MUST set a command in your LaTeXTools.sublime-settings " +
				"file before launching the script builder."
			)
			# I'm not sure this is the best way to handle things...
			raise StopIteration()

		if isinstance(self.cmd, strbase):
			self.cmd = [self.cmd]

		for cmd in self.cmd:
			if isinstance(cmd, strbase):
				if not _ST3:
					cmd = str(cmd)

				cmd = shlex.split(cmd)

				if not _ST3:
					cmd = [unicode(c) for c in cmd]

			replaced_var = False
			for i, component in enumerate(cmd):
				if self.CONTAINS_VARIABLE.search(component):
					template = Template(component)
					component = template.safe_substitute(
						file=self.tex_root,
						file_path=self.tex_dir,
						file_name=self.tex_name,
						file_ext=self.tex_ext,
						file_base_name=self.base_name
					)
					cmd[i] = component
					replaced_var = True

			if not replaced_var:
				cmd.append(self.base_name)

			self.display("Invoking '{0}'... ".format(
				" ".join([quote(s) for s in cmd]))
			)

			yield (
				# run with use_texpath=False as we have already configured
				# the environment above, including the texpath
				external_command(
					cmd, env=env, cwd=self.tex_dir, use_texpath=False
				),
				""
			)

			self.display("done.\n")

			# This is for debugging purposes
			if self.display_log and p.stdout is not None:
				self.display("\nCommand results:\n")
				self.display(self.out)
				self.display("\n\n")
