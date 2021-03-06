import datetime


class NOT_PROVIDED(object):
    pass


class FieldLengthError(Exception):
    pass


def str_padding(length, val):
    """Formats value giving it a right space padding up to a total length of 'length'"""
    return '{0:<{fill}}'.format(val, fill=length)


def int_padding(length, val, direction=">"):
    """Formats value giving it left zeros padding up to a total length of 'length'"""
    return '{0:0{direction}{fill}}'.format(val, direction=direction, fill=length)


def float_padding(length, val, decimals=2):
    """Pads zeros to left and right to assure proper length and precision"""
    return '{0:0>{fill}.{precision}f}'.format(float(val), fill=length, precision=decimals)


def is_blank_string(val):
    return isinstance(val, basestring) and val.strip() == ''


class FixedWidthField(object):
    attname = ''
    auto_truncate = ''
    creation_counter = 0

    def __init__(self, length, default=NOT_PROVIDED):
        self.length = length
        self.default = default

        # Increase the creation counter, and save our local copy.
        self.creation_counter = FixedWidthField.creation_counter
        FixedWidthField.creation_counter += 1

    def __get__(self, instance, txpe):
        try:
            return getattr(instance, self._get_instance_field())
        except AttributeError:
            return self.get_default()

    def __set__(self, instance, val):
        setattr(instance, self._get_instance_field(), self.to_python(val))

    def _get_instance_field(self):
        return "{attname}_{creation_counter}".format(**self.__dict__)

    def has_default(self):
        return self.default is not NOT_PROVIDED

    def get_default(self):
        if self.has_default():
            if callable(self.default):
                return self.default()
            return self.default

    def to_python(self, val):
        if val is None:
            return val
        return str(val).rstrip()

    def to_record(self, val):
        if val is None:
            val = ''
        return str_padding(self.length, val)

    def get_record_value(self, val):
        record_val = self.to_record(val)
        if self.auto_truncate:
            record_val = record_val[:self.length]
        self._check_record_length(record_val)
        return record_val

    def _check_record_length(self, record_val):
        if len(record_val) > self.length:
            err = "'{attname}' value '{0}' is longer than {length} chars.".format(record_val, **self.__dict__)
            raise FieldLengthError(err)


class StringField(FixedWidthField):
    pass


class NewLineField(FixedWidthField):

    def __init__(self):
        super(NewLineField, self).__init__(length=1, default='\n')

    def to_python(self, val):
        if val is None:
            return val
        return str(val)


class PostalCodeField(FixedWidthField):

    def __init__(self):
        super(PostalCodeField, self).__init__(length=9)

    def to_record(self, val):
        if val is None or is_blank_string(val):
            return str_padding(self.length, " ")
        try:
            int(val)
            return int_padding(self.length, val, "<")
        except ValueError:
            return str_padding(self.length, val)


class IntegerField(FixedWidthField):

    def to_python(self, val):
        if val is None or is_blank_string(val):
            return None
        return int(val)

    def to_record(self, val):
        if val is None:
            val = 0
        return int_padding(self.length, val)


class DecimalField(FixedWidthField):

    def __init__(self, length, default=NOT_PROVIDED, decimals=2):
        self.decimals = decimals
        super(DecimalField, self).__init__(length, default)

    def to_python(self, val):
        if val is None or is_blank_string(val):
            return None
        return float(val)

    def to_record(self, val):
        if val is None:
            val = 0
        return float_padding(self.length, val, decimals=self.decimals)


class DateTimeField(FixedWidthField):

    def __init__(self, length, default=NOT_PROVIDED, format="%Y-%m-%d"):
        self.format = format
        super(DateTimeField, self).__init__(length, default)

    def to_python(self, val):
        value_dict = {
            type(None): lambda v: None,
            str: self._format_string_date,
            unicode: self._format_string_date,
            datetime.datetime: lambda v: v,
            datetime.date: lambda v: datetime.datetime(v.year, v.month, v.day),
        }
        return value_dict[type(val)](val)

    def to_record(self, val):
        if not val:
            return str_padding(self.length, '')
        return val.strftime(self.format)

    def _format_string_date(self, val):
        return None if val.strip() == '' else datetime.datetime.strptime(val, self.format)


class DateField(DateTimeField):

    def to_python(self, val):
        result = super(DateField, self).to_python(val)
        if isinstance(result, datetime.datetime):
            return result.date()
        return result


class FragmentField(FixedWidthField):
    """
    Allows you to create a field on a record that is itself a complete
    record. Similar to a ``ListField`` except it only occurs once.


    class Phone(Record):
      area_code = fields.IntegerField(length=3)
      prefix = fields.IntegerField(length=3)
      line_number = fields.IntegerField(length=4)

    class Contact(Record):
      name = fields.StringField(length=100)
      phone_number = fields.FragmentField(record=Phone)
      email = fields.StringField(length=100)

    """

    def __init__(self, record):
        self.record_class = record
        super(FragmentField, self).__init__(len(record))

    def to_python(self, val):
        """
        :returns:
            Always returns an instance of the record class.
        """
        value_dict = {
            type(None): lambda v: self.record_class(),
            str: self.record_class.from_record,
            unicode: self.record_class.from_record,
            self.record_class: lambda v: v,
            dict: lambda v: self.record_class(**v),
        }
        try:
            return value_dict[type(val)](val)
        except KeyError:
            msg = "Redefined field must be a string or {record} instance.".format(
                record=self.record_class.__name__)
            raise TypeError(msg)

    def to_record(self, val):
        """
        :param val:
            val will either be None or an instance of ``self.record_class``
        :returns:
            Always returns a string spaced properly for self.record_class.
        """
        if val is None:
            return self.record_class().to_record()
        return val.to_record()


class ListField(FixedWidthField):
    """
    ListField allows you to have a field made up of a number of
    other records. Similar to COBOL's OCCURS.

    parameters:
      - record: which Record the field is made up of
      - length: how many times that record occurs

    """

    def __init__(self, record, length=1):
        self.record_class = record
        super(ListField, self).__init__(length)

    def _get_records_from_string(self, val):
        records = []
        record_len = len(self.record_class)
        for _ in range(self.length):
            records.append(self.record_class.from_record(val[:record_len]))
            val = val[record_len:]
        return records

    def to_python(self, val):
        value_dict = {
            str: self._get_records_from_string,
            unicode: self._get_records_from_string,
            list: self._sequence_to_python,
            tuple: self._sequence_to_python,
        }
        return value_dict.get(type(val))(val)

    def _sequence_to_python(self, val):
        if all([isinstance(r, dict) for r in val]):
            return [self.record_class(**r) for r in val]
        if not all([isinstance(r, self.record_class) for r in val]):
            msg = "List field must contain instances of '{0}'.".format(self.record_class.__name__)
            raise TypeError(msg)
        return list(val)

    def get_default(self):
        return []

    def to_record(self, val):
        """
        We receive a list of Record classes and must make sure
        we have a complete record we're giving back.
        """
        while len(val) < self.length:
            val.append(self.record_class())
        return ''.join([v.to_record() for v in val])

    def _check_record_length(self, record_val):
        max_record_length = len(self.record_class)
        record_length = len(record_val)
        if record_length > (self.length * max_record_length):
            record_count = record_length / max_record_length
            msg = "'{attname}' contains {cnt} records but can only have {length}.".format(cnt=record_count,
                                                                                          **self.__dict__)
            raise FieldLengthError(msg)
