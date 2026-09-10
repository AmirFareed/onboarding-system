import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import Toggle from '../../components/common/Toggle/Toggle';

// Toggle is a controlled component -- it holds no state of its own, it just
// renders `checked` and reports clicks via `onChange` -- so "clicking toggles
// its state" is really two separate behaviors to verify: the callback fires
// with the inverted value, and the displayed state follows whatever the
// parent does with that callback.
describe('Toggle', () => {
  it('calls onChange with the inverted value when clicked', () => {
    const handleChange = vi.fn();
    render(<Toggle checked={false} onChange={handleChange} aria-label="Test toggle" />);

    fireEvent.click(screen.getByRole('switch'));

    expect(handleChange).toHaveBeenCalledWith(true);
  });

  it('reflects the checked prop once the parent updates it', () => {
    function ControlledToggle() {
      const [checked, setChecked] = useState(false);
      return <Toggle checked={checked} onChange={setChecked} aria-label="Test toggle" />;
    }

    render(<ControlledToggle />);
    const input = screen.getByRole('switch');

    expect(input.checked).toBe(false);
    fireEvent.click(input);
    expect(input.checked).toBe(true);
  });

  it('marks the underlying input disabled so real browsers block interaction', () => {
    render(<Toggle checked={false} onChange={vi.fn()} aria-label="Test toggle" disabled />);

    expect(screen.getByRole('switch')).toBeDisabled();
  });
});
