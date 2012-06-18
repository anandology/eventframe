# -*- coding: utf-8 -*-

from flask import g, abort, flash, url_for, request
from coaster.views import load_models
from baseframe.forms import render_form, render_redirect, render_delete_sqla
from eventframe import app
from eventframe.views import NodeHandler, node_registry
from eventframe.forms import ContentForm, FragmentForm, RedirectForm
from eventframe.models import db, Website, Folder, Node, Page, Post, Fragment, Redirect
from eventframe.views.login import lastuser


# TODO: make handlers request instances and handle complete request within here
# instead of breaking up into three parts

class AutoFormHandler(NodeHandler):
    title_new = u"New node"
    title_edit = u"Edit node"

    def render_form(self, folder, node, form):
        return render_form(form=form, title=self.title_edit if node else self.title_new, submit=u"Save",
            cancel_url=url_for('folder', website=folder.website.name, folder=folder.name))


class ContentHandler(AutoFormHandler):
    form = ContentForm

    def make_form(self, folder, node):
        # TODO: Add support for editing a specific revision
        if node:
            form = self.form(obj=node.revisions.draft)
            if request.method == 'GET':
                form.name.data = node.name
            return form
        else:
            return self.form()

    def process_form(self, folder, node, form):
        if node is None:
            # Creating a new object
            node = self.model(folder=folder, user=g.user)
            db.session.add(node)
        # Name isn't in revision history, so name changes
        # are applied to the node. TODO: Move this into a separate
        # rename action
        node.name = form.name.data
        # Make a revision and apply changes to it
        revision = node.revise()
        form.populate_obj(revision)
        if not node.title:
            # New object. Copy title from first revision
            node.title = revision.title
        if not node.id and not node.name:
            node.make_name()
        db.session.commit()
        # FIXME: Say edited when edited
        flash(u"Created node '%s'." % node.title, 'success')
        return render_redirect(url_for('folder', website=folder.website.name, folder=folder.name), code=303)


class PageHandler(ContentHandler):
    model = Page
    title_new = u"New page"
    title_edit = u"Edit page"


class PostHandler(ContentHandler):
    model = Post
    title_new = u"New blog post"
    title_edit = u"Edit blog post"


class FragmentHandler(ContentHandler):
    model = Fragment
    form = FragmentForm
    title_new = u"New page fragment"
    title_edit = u"Edit page fragment"


class RedirectHandler(AutoFormHandler):
    model = Redirect
    title_new = u"New redirect"
    title_edit = u"Edit redirect"

    def make_form(self, folder, node):
        return RedirectForm(obj=node)

    def process_form(self, folder, node, form):
        if node is None:
            node = self.model(folder=folder, user=g.user)
            db.session.add(node)
        form.populate_obj(node)
        db.session.commit()
        flash(u"Edited redirect '%s'." % node.title, 'success')
        return render_redirect(url_for('folder', website=folder.website.name, folder=folder.name), code=303)


node_registry.register(Page, PageHandler(), render=True)
node_registry.register(Post, PostHandler(), render=True)
node_registry.register(Fragment, FragmentHandler(), render=False)
node_registry.register(Redirect, RedirectHandler(), render=False)


# --- Routes ------------------------------------------------------------------

@app.route('/<website>/<folder>/_new/<type>', methods=['GET', 'POST'])
@app.route('/<website>/_root/_new/<type>', defaults={'folder': u''}, methods=['GET', 'POST'])
@lastuser.requires_permission('siteadmin')
@load_models(
    (Website, {'name': 'website'}, 'website'),
    (Folder, {'name': 'folder', 'website': 'website'}, 'folder'),
    kwargs=True
    )
def node_new(website, folder, kwargs):
    type = kwargs['type']
    if type not in node_registry:
        abort(404)
    record = node_registry[type]
    handler = record.handler
    if handler is None:
        abort(404)
    form = handler.make_form(folder=folder, node=None)
    if form.validate_on_submit():
        return handler.process_form(folder, None, form)
    return handler.render_form(folder, None, form)


@app.route('/<website>/<folder>/<node>/_edit', methods=['GET', 'POST'])
@app.route('/<website>/_root/<node>/_edit', defaults={'folder': u''}, methods=['GET', 'POST'])
@app.route('/<website>/<folder>/_index/_edit', defaults={'node': u''}, methods=['GET', 'POST'])
@app.route('/<website>/_root/_index/_edit', defaults={'folder': u'', 'node': u''}, methods=['GET', 'POST'])
@lastuser.requires_permission('siteadmin')
@load_models(
    (Website, {'name': 'website'}, 'website'),
    (Folder, {'name': 'folder', 'website': 'website'}, 'folder'),
    (Node, {'name': 'node', 'folder': 'folder'}, 'node')
    )
def node_edit(website, folder, node):
    record = node_registry[node.type]
    handler = record.handler
    if handler is None:
        abort(404)
    form = handler.make_form(folder=folder, node=node)
    if form.validate_on_submit():
        return handler.process_form(folder, node, form)
    return handler.render_form(folder, node, form)


@app.route('/<website>/<folder>/<node>/_delete', methods=['GET', 'POST'])
@app.route('/<website>/_root/<node>/_delete', defaults={'folder': u''}, methods=['GET', 'POST'])
@app.route('/<website>/<folder>/_index/_delete', defaults={'node': u''}, methods=['GET', 'POST'])
@app.route('/<website>/_root/_index/_delete', defaults={'folder': u'', 'node': u''}, methods=['GET', 'POST'])
@lastuser.requires_permission('siteadmin')
@load_models(
    (Website, {'name': 'website'}, 'website'),
    (Folder, {'name': 'folder', 'website': 'website'}, 'folder'),
    (Page, {'name': 'node', 'folder': 'folder'}, 'node')
    )
def node_delete(website, folder, node):
    return render_delete_sqla(node, db, title=u"Confirm delete",
        message=u"Delete node '%s'? This is permanent. There is no undo." % website.title,
        success=u"You have deleted node '%s'." % node.title,
        next=url_for('folder', website=website.name, folder=folder.name))
