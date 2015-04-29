# ST2/ST3 compat
from __future__ import print_function
import sublime
if sublime.version() < '3000':
	_ST3 = False
	# we are on ST2 and Python 2.X
	import getTeXRoot
else:
	_ST3 = True
	from . import getTeXRoot


import sublime_plugin
import os

class Delete_temp_filesCommand(sublime_plugin.WindowCommand):
	def run(self):
		# Retrieve file and dirname.
		view = self.window.active_view()
		self.file_name = getTeXRoot.get_tex_root(view)
		if not os.path.isfile(self.file_name):
			sublime.error_message(self.file_name + ": file not found.")
			return

		self.path = os.path.dirname(self.file_name)

		# Delete the files.
		temp_exts = set(['.blg','.bbl','.aux','.log','.brf','.nlo','.out','.dvi','.ps',
			'.lof','.toc','.fls','.fdb_latexmk','.pdfsync','.synctex.gz','.ind','.ilg','.idx'])
		ignored_folders = ['.git','.svn']

		for dir_path, dir_names, file_names in os.walk(self.path):
			dir_names[:] = [d for d in dir_names if d not in ignored_folders]
			for file_name in file_names:
				for ext in temp_exts:
					if file_name.endswith(ext):
						file_name_to_del = os.path.join(dir_path, file_name)
						if os.path.exists(file_name_to_del):
							os.remove(file_name_to_del)

		sublime.status_message("Deleted temp files")