# -*- coding: utf-8 -*-

from datetime import datetime
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm.collections import attribute_mapped_collection
from urlparse import urljoin
from flask import g, url_for
from coaster import newid, parse_isoformat
from eventframe.models import db, TimestampMixin, BaseMixin, BaseNameMixin, BaseScopedNameMixin
from eventframe.models.user import User

__all__ = ['Website', 'Hostname', 'LoginCode', 'Folder', 'Node', 'NodeMixin']


def default_user_id():
    return g.user.id if g.user else None


class Website(BaseNameMixin, db.Model):
    __tablename__ = 'website'
    #: URL to the website
    url = db.Column(db.Unicode(80), nullable=False, default=u'')
    #: Theme that this website uses as the default (folders can override)
    theme = db.Column(db.Unicode(80), nullable=False, default=u'default')
    #: Typekit code, if used
    typekit_code = db.Column(db.Unicode(20), nullable=False, default=u'')
    #: Google Analytics code, if used
    googleanalytics_code = db.Column(db.Unicode(20), nullable=False, default=u'')

    _hostnames = db.relationship("Hostname", cascade='all, delete-orphan', backref='website')
    hostnames = association_proxy('_hostnames', 'name',
        creator=lambda name: Hostname.get(name=name))

    def __init__(self, **kwargs):
        super(Website, self).__init__(**kwargs)
        root = Folder(name=u'', title=u'', website=self)
        self.folders.append(root)
        #root.pages[0].template = u'index.html'

    def __repr__(self):
        return u'<Website %s "%s">' % (self.name, self.title)


class Hostname(BaseMixin, db.Model):
    __tablename__ = 'hostname'
    #: Hostname that a website may be accessed at. Typically name:port
    name = db.Column(db.String(80), unique=True, nullable=False)
    #: Website this hostname applies to
    website_id = db.Column(db.Integer, db.ForeignKey('website.id'), nullable=False)

    def __repr__(self):
        return u'<Hostname %s>' % self.name

    @classmethod
    def get(cls, name, website=None):
        hostname = cls.query.filter_by(name=name).first()
        return hostname or cls(name=name, website=website)


class LoginCode(BaseMixin, db.Model):
    __tablename__ = 'logincode'
    #: Tracking code to enable users to login to an event website
    code = db.Column(db.Unicode(22), nullable=False, unique=True)
    #: User who logged in
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, default=None)
    user = db.relationship(User)
    #: URL on event website to return user to
    next_url = db.Column(db.Unicode(250), nullable=False)
    #: Login handler URL on event website
    return_url = db.Column(db.Unicode(250), nullable=False)

    def __init__(self, **kwargs):
        super(LoginCode, self).__init__(**kwargs)
        self.code = newid()


class Folder(BaseScopedNameMixin, db.Model):
    __tablename__ = 'folder'
    #: Website this folder is under
    website_id = db.Column(db.Integer, db.ForeignKey('website.id'), nullable=False)

    _theme = db.Column("theme", db.Unicode(80), nullable=False, default=u'')

    website = db.relationship(Website,
        backref=db.backref('folders', order_by='Folder.name', cascade='all, delete-orphan'))
    parent = db.synonym('website')
    __table_args__ = (db.UniqueConstraint('name', 'website_id'),)

    @property
    def theme(self):
        return self._theme or self.website.theme

    @theme.setter
    def theme(self, value):
        self._theme = value

    #: Theme used by the folder. Defaults to the website's theme.
    theme = db.synonym('_theme', descriptor=theme)

    def __init__(self, **kwargs):
        super(Folder, self).__init__(**kwargs)
        #index = Page(name=u'', title=u'Index', folder=self, template=u'page.html')
        #index.name = u''  # Reset it to a blank
        #self.pages.append(index)

    def __repr__(self):
        return u'<Folder %s at %s>' % (self.name or '(root)', self.website.name)

    def view_url(self):
        """
        Returns a view URL based on the website's URL field.
        """
        return urljoin(self.website.url, self.name)


class Property(BaseMixin, db.Model):
    __tablename__ = 'property'
    node_id = db.Column(None, db.ForeignKey('node.id'), nullable=False)
    name = db.Column(db.Unicode(40), nullable=False)
    value = db.Column(db.Unicode(250), nullable=False)

    __table_args__ = (db.UniqueConstraint('name', 'node_id'),)


_marker = []


class _NodeProperties(dict):
    """
    Requires self.node to point to a node.
    """
    def __init__(self, *args, **kwargs):
        self.node = kwargs.pop('node')
        self.update(*args, **kwargs)

    def update(self, *args, **kwargs):
        for k, v in dict(*args, **kwargs).iteritems():
            self[k] = v

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        del self.node.node_properties[key]

    def pop(self, key, default=_marker):
        if default is _marker:
            self.node.node_properties.pop(key, default)
            return dict.pop(self, key)
        else:
            self.node.node_properties(key, default)
            return dict.pop(self, key, default)

    def __setitem__(self, key, value):
        if isinstance(value, Property):
            dict.__setitem__(self, key, value.value)
        else:
            value = unicode(value)  # Since Property.value = db.Unicode
            dict.__setitem__(self, key, value)
            if key in self.node.node_properties:
                self.node.node_properties[key].value = value
            else:
                prop = Property(name=key, value=value)
                self.node.node_properties[key] = prop


class Node(BaseScopedNameMixin, db.Model):
    __tablename__ = 'node'
    #: Id of the node across sites (staging, production, etc) for import/export
    uuid = db.Column(db.Unicode(22), unique=True, default=newid, nullable=False)
    #: User who made this node
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, default=default_user_id)
    user = db.relationship(User)
    #: Folder in which this node is located
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=False)
    folder = db.relationship(Folder,
        backref=db.backref('nodes', order_by='Node.name', cascade='all, delete-orphan'))
    parent = db.synonym('folder')
    #: Publication date
    published_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    #: Type of node, for polymorphic identity
    type = db.Column('type', db.Unicode(20))
    __table_args__ = (db.UniqueConstraint('name', 'folder_id'),)
    __mapper_args__ = {'polymorphic_on': type}

    node_properties = db.relationship(Property,
        cascade='all, delete-orphan',
        collection_class=attribute_mapped_collection('name'),
        backref='node')

    @property
    def properties(self):
        if not hasattr(self, '_cached_properties'):
            self._cached_properties = _NodeProperties(self.node_properties, node=self)
        return self._cached_properties

    @properties.setter
    def properties(self, value):
        if not isinstance(value, dict):
            raise ValueError("Value is not a dictionary")
        for key in list(self.node_properties.keys()):
            if key not in value:
                self.node_properties.pop(key)
        self._cached_properties = _NodeProperties(value, node=self)

    def as_json(self):
        return {
            'uuid': self.uuid,
            'name': self.name,
            'title': self.title,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z',
            'published_at': self.published_at.isoformat() + 'Z',
            'userid': self.user.userid,
            'type': self.type,
            'properties': self.properties,
        }

    def import_from(self, data):
        self.uuid = data['uuid']
        self.name = data['name']
        self.title = data['title']
        self.published_at = parse_isoformat(data['published_at'])
        self.properties = data['properties']

    def import_from_internal(self, data):
        # Only required for nodes that keep internal references to other nodes
        pass

    def url(self):
        """
        Return a URL to this node.
        """
        if self.folder.name == u'':
            return url_for('folder', folder=self.name)
        else:
            return url_for('node', folder=self.folder.name, node=self.name)


class NodeMixin(TimestampMixin):
    @declared_attr
    def id(cls):
        """Link back to node"""
        return db.Column(db.Integer, db.ForeignKey('node.id'), primary_key=True, nullable=False)

    @declared_attr
    def __mapper_args__(cls):
        """Use the table name as the polymorphic identifier"""
        return {'polymorphic_identity': cls.__tablename__}

    @declared_attr
    def __title__(cls):
        """Create a title for the type, from the class name"""
        return cls.__tablename__.replace('_', ' ').title()
