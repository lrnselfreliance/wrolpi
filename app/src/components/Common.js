import React from "react";
import Pagination from "react-bootstrap/Pagination";

const API_URI = process.env.REACT_APP_API ? process.env.REACT_APP_API : '127.0.0.1:8080';
const VIDEOS_API = `http://${API_URI}/api/videos`;

class Paginator extends React.Component {

    setOffset(offset) {
        this.setState({'offset': offset});
    }

    getPagination() {
        // The amount of items that will be shown
        let item_count = 8;

        let total = this.state.total;
        let limit = this.state.limit;
        let offset = this.state.offset;

        // Generate all offsets that can exist
        let items = [];
        let last = null;
        for (let i = 0; i <= total; i = i + limit) {
            items.push(i);
            last = i;
        }

        // Reduce the offsets to those around the current offset
        let current_idx = items.indexOf(offset);
        // There can't be less than zero offset
        let start = Math.max(0, current_idx - (item_count / 2));
        items = items.slice(start, start + item_count);

        return (
            <Pagination>
                {/* first and last should always be present */}
                {items[0] !== 0 && <Pagination.First onClick={() => this.setOffset(0)}/>}
                {items.map((i) =>
                    <Pagination.Item
                        active={i === offset}
                        key={i}
                        onClick={() => this.setOffset(i)}
                    >
                        {(i / limit) + 1}
                    </Pagination.Item>)}
                {items[items.length-1] !== last && <Pagination.Last onClick={() => this.setOffset(last)}/>}
            </Pagination>
        )
    }
}

export default Paginator;
export {VIDEOS_API};