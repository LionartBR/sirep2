(function (global) {
  'use strict';

  const onlyDigits = (value) => String(value ?? '')
    .replace(/\D+/g, '');

  const formatCnpj = (digits) => {
    if (digits.length !== 14) {
      return digits;
    }
    return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
  };

  const formatCpf = (digits) => {
    if (digits.length !== 11) {
      return digits;
    }
    return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
  };

  const formatDocument = (value) => {
    const raw = String(value ?? '').trim();
    if (!raw) {
      return '';
    }

    const digits = onlyDigits(raw);
    if (!digits) {
      return raw;
    }

    if (digits.length === 14) {
      return formatCnpj(digits);
    }

    if (digits.length === 11) {
      return formatCpf(digits);
    }

    return digits;
  };

  global.SirepUtils = Object.assign({}, global.SirepUtils, {
    onlyDigits,
    formatCnpj,
    formatCpf,
    formatDocument,
  });
})(typeof window !== 'undefined' ? window : this);
