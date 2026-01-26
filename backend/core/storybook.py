import re

def generate_stories(component_code: str, component_name: str = "Component") -> str:
    """
    Generates a basic Storybook file content for the given component.
    """
    # Attempt to extract component name if not provided or generic
    # Pattern 1: export default function ComponentName
    match_func = re.search(r"export\s+default\s+function\s+(\w+)", component_code)
    # Pattern 2: const ComponentName = ... export default ComponentName
    match_const = re.search(r"const\s+(\w+)\s*=\s*\(", component_code)
    
    if match_func:
        component_name = match_func.group(1)
    elif match_const:
        component_name = match_const.group(1)
        
    stories_code = f"""import type {{ Meta, StoryObj }} from '@storybook/react';
import {component_name} from './{component_name}';

const meta = {{
  title: 'Generated/{component_name}',
  component: {component_name},
  parameters: {{
    layout: 'centered',
  }},
  tags: ['autodocs'],
}} satisfies Meta<typeof {component_name}>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {{
  args: {{}},
}};
"""
    return stories_code
