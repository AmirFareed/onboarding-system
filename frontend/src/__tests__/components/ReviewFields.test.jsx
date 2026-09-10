import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ReviewFields from '../../components/humanReview/ReviewFields/ReviewFields';

function fieldItem(overrides) {
  return {
    field_name: 'account_holder',
    document_id: 1,
    file_name: 'amc.pdf',
    extracted_value: 'SAMPLE AUTHORITY',
    normalized_value: 'SAMPLE AUTHORITY',
    confidence_score: 0.92,
    confidence_source: 'exact_match',
    verification_status: 'CONFIRMED',
    human_corrected_value: null,
    human_verified: false,
    ...overrides,
  };
}

describe('ReviewFields', () => {
  it('shows the empty state when there are no fields', () => {
    render(<ReviewFields fields={[]} corrections={[]} onCorrectionsChange={vi.fn()} />);

    expect(
      screen.getByText(/no extracted fields are available for this application/i)
    ).toBeInTheDocument();
  });

  it('renders a row with the human-readable field name, values, source document and confidence', () => {
    render(
      <ReviewFields fields={[fieldItem()]} corrections={[]} onCorrectionsChange={vi.fn()} />
    );

    // Human-readable label from getFieldLabel
    expect(screen.getByText('Account Holder')).toBeInTheDocument();
    expect(screen.getByText('amc.pdf')).toBeInTheDocument();
    expect(screen.getAllByText('SAMPLE AUTHORITY')).toHaveLength(2);
    expect(screen.getByText('92%')).toBeInTheDocument();
  });

  it('marks a field reviewed and hides the Correct action once human_verified is set', () => {
    render(
      <ReviewFields
        fields={[fieldItem({ human_verified: true })]}
        corrections={[]}
        onCorrectionsChange={vi.fn()}
      />
    );

    expect(screen.getByText('Reviewed')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument();
  });

  it('shows Human Corrected status when field has a human_corrected_value', () => {
    render(
      <ReviewFields
        fields={[fieldItem({ human_corrected_value: 'CORRECTED AUTHORITY' })]}
        corrections={[]}
        onCorrectionsChange={vi.fn()}
      />
    );

    expect(screen.getByText('Human Corrected')).toBeInTheDocument();
    expect(screen.getByText(/corrected: corrected authority/i)).toBeInTheDocument();
  });

  it('starting a correction adds an entry defaulting to the normalized value', () => {
    const onCorrectionsChange = vi.fn();
    render(
      <ReviewFields fields={[fieldItem()]} corrections={[]} onCorrectionsChange={onCorrectionsChange} />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Correct' }));

    expect(onCorrectionsChange).toHaveBeenCalledWith([
      {
        document_id: 1,
        field_name: 'account_holder',
        corrected_value: 'SAMPLE AUTHORITY',
        reason: '',
      },
    ]);
  });

  it('falls back to the extracted value when no normalized value exists', () => {
    const onCorrectionsChange = vi.fn();
    render(
      <ReviewFields
        fields={[fieldItem({ normalized_value: null, extracted_value: 'RAW VALUE' })]}
        corrections={[]}
        onCorrectionsChange={onCorrectionsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Correct' }));

    expect(onCorrectionsChange).toHaveBeenCalledWith([
      expect.objectContaining({ corrected_value: 'RAW VALUE' }),
    ]);
  });

  it('editing the corrected value updates only that correction entry', () => {
    const onCorrectionsChange = vi.fn();
    const corrections = [
      { document_id: 1, field_name: 'account_holder', corrected_value: 'SAMPLE AUTHORITY', reason: '' },
    ];
    render(
      <ReviewFields
        fields={[fieldItem()]}
        corrections={corrections}
        onCorrectionsChange={onCorrectionsChange}
      />
    );

    const input = screen.getByLabelText(/corrected value/i);
    fireEvent.change(input, { target: { value: 'X' } });

    expect(onCorrectionsChange).toHaveBeenLastCalledWith([
      {
        document_id: 1,
        field_name: 'account_holder',
        corrected_value: 'X',
        reason: '',
      },
    ]);
  });

  it('editing the reason updates only the reason', () => {
    const onCorrectionsChange = vi.fn();
    const corrections = [
      { document_id: 1, field_name: 'account_holder', corrected_value: 'SAMPLE AUTHORITY', reason: '' },
    ];
    render(
      <ReviewFields
        fields={[fieldItem()]}
        corrections={corrections}
        onCorrectionsChange={onCorrectionsChange}
      />
    );

    const input = screen.getByLabelText(/reason/i);
    fireEvent.change(input, { target: { value: 'Y' } });

    expect(onCorrectionsChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ corrected_value: 'SAMPLE AUTHORITY', reason: 'Y' }),
    ]);
  });

  it('cancelling a correction removes it', () => {
    const onCorrectionsChange = vi.fn();
    const corrections = [
      { document_id: 1, field_name: 'account_holder', corrected_value: 'SAMPLE AUTHORITY', reason: '' },
    ];
    render(
      <ReviewFields
        fields={[fieldItem()]}
        corrections={corrections}
        onCorrectionsChange={onCorrectionsChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(onCorrectionsChange).toHaveBeenCalledWith([]);
  });

  it('keeps corrections on two documents with the same field name independent', () => {
    const onCorrectionsChange = vi.fn();
    const fields = [
      fieldItem({ document_id: 1, file_name: 'doc-a.pdf', extracted_value: 'A VALUE', normalized_value: 'A VALUE' }),
      fieldItem({ document_id: 2, file_name: 'doc-b.pdf', extracted_value: 'B VALUE', normalized_value: 'B VALUE' }),
    ];
    const corrections = [
      { document_id: 1, field_name: 'account_holder', corrected_value: 'A VALUE', reason: '' },
    ];
    render(
      <ReviewFields fields={fields} corrections={corrections} onCorrectionsChange={onCorrectionsChange} />
    );

    // Only document 1's row is mid-correction; document 2's Correct button
    // must still be available, not blocked by document 1's in-progress edit.
    expect(screen.getAllByRole('button', { name: 'Correct' })).toHaveLength(1);

    fireEvent.click(screen.getAllByRole('button', { name: 'Correct' })[0]);

    expect(onCorrectionsChange).toHaveBeenCalledWith([
      ...corrections,
      {
        document_id: 2,
        field_name: 'account_holder',
        corrected_value: 'B VALUE',
        reason: '',
      },
    ]);
  });

  it('does not render a Correct action when readOnly', () => {
    render(
      <ReviewFields fields={[fieldItem()]} corrections={[]} onCorrectionsChange={vi.fn()} readOnly />
    );

    expect(screen.queryByRole('button', { name: 'Correct' })).not.toBeInTheDocument();
  });

  it('shows IBAN mismatch warning for account_number fields with IBAN-format values', () => {
    render(
      <ReviewFields
        fields={[fieldItem({ field_name: 'account_number', extracted_value: 'PK54KHYB5188003003755532' })]}
        corrections={[]}
        onCorrectionsChange={vi.fn()}
      />
    );

    expect(screen.getByText(/possible extraction mismatch/i)).toBeInTheDocument();
  });
});
